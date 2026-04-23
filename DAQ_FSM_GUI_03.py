import os
import glob
import csv
import time
import subprocess
import tkinter as tk
from tkinter import ttk
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from enum import IntEnum
import RPi.GPIO as GPIO

# =========================================================
# LOAD 1-WIRE DRIVERS
# =========================================================
os.system('modprobe w1-gpio')
os.system('modprobe w1-therm')

BASE_DIR = '/sys/bus/w1/devices/'

# ✅ SENSOR MAP (UPDATED)
SENSOR_MAP = {
    "28-00000034c7d5": "hex_inlet",
    "28-00000037e0c4": "hex_outlet",
    "28-00000037009c": "heater_outlet",   # tank equivalent
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

def relay_level(device_name: str, command_on: bool) -> int:
    active_high = ACTIVE_HIGH[device_name]
    if active_high:
        return GPIO.HIGH if command_on else GPIO.LOW
    else:
        return GPIO.LOW if command_on else GPIO.HIGH

def setup_gpio():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    GPIO.setup(RELAY_PIN_SOLENOID, GPIO.OUT)
    GPIO.setup(RELAY_PIN_FAN, GPIO.OUT)
    GPIO.setup(RELAY_PIN_PUMP, GPIO.OUT)
    GPIO.setup(RELAY_PIN_HEATER, GPIO.OUT)

    set_outputs(False, False, False, False)

def set_outputs(valve_cmd, blower_cmd, pump_cmd, heater_cmd):
    GPIO.output(RELAY_PIN_SOLENOID, relay_level("solenoid", valve_cmd))
    GPIO.output(RELAY_PIN_FAN, relay_level("fan", blower_cmd))
    GPIO.output(RELAY_PIN_PUMP, relay_level("pump", pump_cmd))
    GPIO.output(RELAY_PIN_HEATER, relay_level("heater", heater_cmd))

# =========================================================
# SENSORS
# =========================================================
def get_device_folders():
    return glob.glob(BASE_DIR + '28*')

def read_temp(device_file):
    try:
        with open(device_file, 'r') as f:
            lines = f.readlines()

        while lines[0].strip()[-3:] != 'YES':
            time.sleep(0.2)
            with open(device_file, 'r') as f:
                lines = f.readlines()

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
# FSM (MINIMAL CHANGE)
# =========================================================
desired_temp = 25.0

def read_desired_temperature():
    return desired_temp

def read_peak_state():
    return 1

def tes_ahu_simple(T_amb, T_des, T_tank, peak_state):
    T_full = 60.0
    T_low = 40.0

    need_heat = T_amb < T_des

    if need_heat:
        if peak_state == 1:
            if T_tank > T_low:
                return AHUState.VENT, TESState.DISCHARGE, 1
            else:
                return AHUState.NORMAL, TESState.IDLE, 2
        else:
            if T_tank < T_full:
                return AHUState.NORMAL, TESState.CHARGING, 3
            else:
                return AHUState.NORMAL, TESState.IDLE, 4
    else:
        if not peak_state and T_tank < T_full:
            return AHUState.IDLE, TESState.CHARGING, 6
        else:
            return AHUState.IDLE, TESState.IDLE, 7

def actuation_fsm(ahu_state, tes_state):
    valve_cmd = (tes_state == TESState.DISCHARGE)
    pump_cmd = (tes_state != TESState.IDLE)
    heater_cmd = (tes_state == TESState.CHARGING)
    blower_cmd = (ahu_state == AHUState.VENT and tes_state == TESState.DISCHARGE)
    return valve_cmd, blower_cmd, pump_cmd, heater_cmd

# =========================================================
# LOGGING
# =========================================================
def initialize_log():
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'w', newline='') as f:
            csv.writer(f).writerow(["time","T_amb","T_tank","state"])

def log_data(Ta, Tt, state):
    with open(LOG_FILE, 'a', newline='') as f:
        csv.writer(f).writerow([time.strftime("%H:%M:%S"), Ta, Tt, state])

# =========================================================
# SYSTEM STEP (KEY INTEGRATION)
# =========================================================
def system_step():
    global desired_temp

    T_amb = read_temp_smtc(5)
    sensors = read_all_sensors()

    T_tank = sensors.get("heater_outlet")

    if T_amb is None or T_tank is None:
        return None

    T_des = read_desired_temperature()
    peak_state = read_peak_state()

    ahu_state, tes_state, case_id = tes_ahu_simple(
        T_amb, T_des, T_tank, peak_state
    )

    valve_cmd, blower_cmd, pump_cmd, heater_cmd = actuation_fsm(
        ahu_state, tes_state
    )

    if T_tank > 70:
        heater_cmd = False

    set_outputs(valve_cmd, blower_cmd, pump_cmd, heater_cmd)

    log_data(T_amb, T_tank, ahu_state.name)

    return {
        "T_amb": T_amb,
        "T_tank": T_tank,
        "sensors": sensors,
        "state": ahu_state.name
    }

# =========================================================
# GUI (UNCHANGED STRUCTURE — ONLY INTEGRATION ADDED)
# =========================================================
root = tk.Tk()
root.title("DC House Thermostat")
root.geometry("1200x650")
root.configure(bg="#0b0f14")

current_temp = tk.DoubleVar(value=22.0)
target_temp = tk.DoubleVar(value=25.0)
system_state = tk.StringVar(value="Idle")

status_label = tk.Label(root, text="Idle")
status_label.pack()

# =========================================================
# GUI UPDATE LOOP (NEW)
# =========================================================
def update_system():
    data = system_step()

    if data:
        current_temp.set(data["T_amb"])
        system_state.set(data["state"])
        status_label.config(text=data["state"])

    root.after(2000, update_system)

# =========================================================
# GUI → FSM CONTROL (NEW ONLY)
# =========================================================
def update_target(val=None):
    global desired_temp
    desired_temp = float(val)

def change_temp(delta):
    global desired_temp
    desired_temp = max(15, min(30, desired_temp + delta))
    target_temp.set(desired_temp)

# =========================================================
# KEEP YOUR ORIGINAL GUI BELOW (UNCHANGED IN YOUR FILE)
# =========================================================

# NOTE:
# (Your full GUI code stays EXACTLY as you wrote it — no edits needed)

# =========================================================
# START
# =========================================================
setup_gpio()
initialize_log()

update_system()
root.mainloop()
