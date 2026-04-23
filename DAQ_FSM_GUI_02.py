import os
import glob
import csv
import time
import subprocess
import tkinter as tk
from enum import IntEnum
import RPi.GPIO as GPIO

# =========================================================
# LOAD 1-WIRE
# =========================================================
os.system('modprobe w1-gpio')
os.system('modprobe w1-therm')

BASE_DIR = '/sys/bus/w1/devices/'

# ✅ YOUR SENSOR MAP
SENSOR_MAP = {
    "28-00000034c7d5": "hex_inlet",
    "28-00000037e0c4": "hex_outlet",
    "28-00000037009c": "heater_outlet",   # used as tank
    "28-0000005b080d": "heater_inlet",
}

LOG_FILE = "tes_ahu_log.csv"

# =========================================================
# STATES
# =========================================================
class AHUState(IntEnum):
    IDLE = 0
    NORMAL = 1
    VENT = 2

class TESState(IntEnum):
    IDLE = 0
    CHARGING = 1
    DISCHARGE = 2

# =========================================================
# GPIO
# =========================================================
RELAY_PIN_SOLENOID = 23
RELAY_PIN_FAN = 24
RELAY_PIN_PUMP = 17
RELAY_PIN_HEATER = 27

ACTIVE_HIGH = {
    "solenoid": False,
    "fan": True,
    "pump": True,
    "heater": True,
}

def relay_level(device, cmd):
    if ACTIVE_HIGH[device]:
        return GPIO.HIGH if cmd else GPIO.LOW
    else:
        return GPIO.LOW if cmd else GPIO.HIGH

def setup_gpio():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    GPIO.setup(RELAY_PIN_SOLENOID, GPIO.OUT)
    GPIO.setup(RELAY_PIN_FAN, GPIO.OUT)
    GPIO.setup(RELAY_PIN_PUMP, GPIO.OUT)
    GPIO.setup(RELAY_PIN_HEATER, GPIO.OUT)

    set_outputs(False, False, False, False)

def set_outputs(v, b, p, h):
    GPIO.output(RELAY_PIN_SOLENOID, relay_level("solenoid", v))
    GPIO.output(RELAY_PIN_FAN, relay_level("fan", b))
    GPIO.output(RELAY_PIN_PUMP, relay_level("pump", p))
    GPIO.output(RELAY_PIN_HEATER, relay_level("heater", h))

# =========================================================
# SENSOR READING
# =========================================================
def get_device_folders():
    return glob.glob(BASE_DIR + '28*')

def read_temp(device_file):
    try:
        with open(device_file, 'r') as f:
            lines = f.readlines()

        retry = 0
        while lines[0].strip()[-3:] != 'YES':
            time.sleep(0.2)
            with open(device_file, 'r') as f:
                lines = f.readlines()
            retry += 1
            if retry > 5:
                return None

        pos = lines[1].find('t=')
        if pos != -1:
            return float(lines[1][pos+2:]) / 1000.0
    except:
        return None

def read_all_sensors():
    data = {}
    for folder in get_device_folders():
        dev = folder.split('/')[-1]
        temp = read_temp(folder + '/w1_slave')

        if temp is not None and dev in SENSOR_MAP:
            data[SENSOR_MAP[dev]] = temp

    return data

def read_temp_smtc(channel):
    result = subprocess.run(
        ["smtc", "analog", "read", str(channel)],
        capture_output=True,
        text=True
    )
    try:
        return float(result.stdout.strip())
    except:
        return None

# =========================================================
# FSM
# =========================================================
desired_temp = 25.0

def read_desired_temperature():
    return desired_temp

def read_peak_state():
    return 1

def tes_ahu_simple(T_amb, T_des, T_tank, peak):
    T_full, T_low = 60, 40
    need_heat = T_amb < T_des

    if need_heat:
        if peak:
            return (AHUState.VENT, TESState.DISCHARGE, 1) if T_tank > T_low else (AHUState.NORMAL, TESState.IDLE, 2)
        else:
            return (AHUState.NORMAL, TESState.CHARGING, 3) if T_tank < T_full else (AHUState.NORMAL, TESState.IDLE, 4)
    else:
        return (AHUState.IDLE, TESState.CHARGING, 6) if (not peak and T_tank < T_full) else (AHUState.IDLE, TESState.IDLE, 7)

def actuation_fsm(a, t):
    valve = (t == TESState.DISCHARGE)
    pump = (t != TESState.IDLE)
    heater = (t == TESState.CHARGING)
    blower = (a == AHUState.VENT and t == TESState.DISCHARGE)
    return valve, blower, pump, heater

# =========================================================
# LOGGING
# =========================================================
def initialize_log():
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'w', newline='') as f:
            csv.writer(f).writerow([
                "time","T_amb","hex_in","hex_out","heater_in","heater_out","state"
            ])

def log_data(Ta, sensors, state):
    with open(LOG_FILE, 'a', newline='') as f:
        csv.writer(f).writerow([
            time.strftime("%H:%M:%S"),
            Ta,
            sensors.get("hex_inlet"),
            sensors.get("hex_outlet"),
            sensors.get("heater_inlet"),
            sensors.get("heater_outlet"),
            state
        ])

# =========================================================
# SYSTEM STEP
# =========================================================
def system_step():
    global desired_temp

    T_amb = read_temp_smtc(5)
    sensors = read_all_sensors()

    # ✅ Use heater_outlet as tank temp
    T_tank = sensors.get("heater_outlet")

    if T_amb is None or T_tank is None:
        return None

    ahu, tes, case = tes_ahu_simple(
        T_amb,
        desired_temp,
        T_tank,
        read_peak_state()
    )

    valve, blower, pump, heater = actuation_fsm(ahu, tes)

    set_outputs(valve, blower, pump, heater)
    log_data(T_amb, sensors, ahu.name)

    return T_amb, sensors, ahu.name

# =========================================================
# GUI
# =========================================================
root = tk.Tk()
root.title("Thermostat")
root.geometry("500x400")

current_temp = tk.DoubleVar()
target_temp = tk.DoubleVar(value=25.0)
system_state = tk.StringVar(value="Idle")

label_temp = tk.Label(root, font=("Arial", 24))
label_temp.pack()

label_state = tk.Label(root, font=("Arial", 14))
label_state.pack()

label_sensors = tk.Label(root, font=("Arial", 10), justify="left")
label_sensors.pack(pady=10)

def update_system():
    result = system_step()

    if result:
        Ta, sensors, state = result

        current_temp.set(Ta)
        system_state.set(state)

        label_temp.config(text=f"{Ta:.2f} °C")
        label_state.config(text=f"State: {state}")

        sensor_text = (
            f"HEX In: {sensors.get('hex_inlet', '--')}\n"
            f"HEX Out: {sensors.get('hex_outlet', '--')}\n"
            f"Heater In: {sensors.get('heater_inlet', '--')}\n"
            f"Heater Out: {sensors.get('heater_outlet', '--')}"
        )
        label_sensors.config(text=sensor_text)

    root.after(2000, update_system)

def increase_temp():
    global desired_temp
    desired_temp += 0.5
    target_temp.set(desired_temp)

def decrease_temp():
    global desired_temp
    desired_temp -= 0.5
    target_temp.set(desired_temp)

tk.Button(root, text="+", command=increase_temp).pack()
tk.Button(root, text="-", command=decrease_temp).pack()

tk.Label(root, textvariable=target_temp).pack()

# =========================================================
# START
# =========================================================
setup_gpio()
initialize_log()

update_system()
root.mainloop()
