import os
import glob
import csv
import time
import subprocess
from enum import IntEnum
import pandas as pd   # ✅ ADDED

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False

    class MockGPIO:
        BCM = "BCM"
        OUT = "OUT"
        HIGH = 1
        LOW = 0
        def setmode(self, *args, **kwargs): pass
        def setwarnings(self, *args, **kwargs): pass
        def setup(self, *args, **kwargs): pass
        def output(self, *args, **kwargs): pass
        def cleanup(self, *args, **kwargs): pass

    GPIO = MockGPIO()

# =========================================================
# FILES
# =========================================================
LOG_FILE = "continuous_test_log.csv"
EXCEL_FILE = "continuous_test_log.xlsx"   # ✅ ADDED

# =========================================================
# ENERGY + RUNTIME TRACKING (NEW)
# =========================================================
POWER_RATINGS = {
    "pump": 100,      # W
    "heater": 1440,  # W
    "fan": 4,       # W
    "valve": 10,     # W
}

# =========================================================
# LOAD 1-WIRE
# =========================================================
os.system("modprobe w1-gpio")
os.system("modprobe w1-therm")

BASE_DIR = "/sys/bus/w1/devices/"

# =========================================================
# TEST MATRIX
# =========================================================
CONTINUOUS_TEST = [
    {"sim_hour": i, "peak_state": 1 if 14 <= i <= 19 else 0,
     "desired_temp": (21 if i < 5 else 24 if i < 14 else 27 if i < 20 else 22)}
    for i in range(24)
]

MINUTE_DURATION_SEC = 60

# =========================================================
# SENSOR MAP
# =========================================================
SENSOR_MAP = {
    "28-00000034c7d5": "hex_inlet",
    "28-00000037e0c4": "hex_outlet",
    "28-00000037009c": "tank_outlet",
    "28-0000005b080d": "tank_inlet",
}

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

def relay_level(name, on):
    return GPIO.HIGH if (on == ACTIVE_HIGH[name]) else GPIO.LOW

def setup_gpio():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    for pin in [RELAY_PIN_SOLENOID, RELAY_PIN_FAN, RELAY_PIN_PUMP, RELAY_PIN_HEATER]:
        GPIO.setup(pin, GPIO.OUT)
    set_outputs(False, False, False, False)

def set_outputs(v, b, p, h):
    GPIO.output(RELAY_PIN_SOLENOID, relay_level("solenoid", v))
    GPIO.output(RELAY_PIN_FAN, relay_level("fan", b))
    GPIO.output(RELAY_PIN_PUMP, relay_level("pump", p))
    GPIO.output(RELAY_PIN_HEATER, relay_level("heater", h))

# =========================================================
# SENSOR READ
# =========================================================
def get_device_folders():
    return glob.glob(BASE_DIR + "28*")

def read_temp(file):
    try:
        with open(file) as f:
            lines = f.readlines()
        if "YES" not in lines[0]:
            return None
        return float(lines[1].split("t=")[-1]) / 1000
    except:
        return None

def read_all_sensors():
    data = {k: None for k in SENSOR_MAP.values()}
    for folder in get_device_folders():
        dev = folder.split("/")[-1]
        temp = read_temp(folder + "/w1_slave")
        if dev in SENSOR_MAP:
            data[SENSOR_MAP[dev]] = temp
    return data

def read_temp_smtc(ch):
    try:
        out = subprocess.run(["smtc", "analog", "read", str(ch)],
                             capture_output=True, text=True, timeout=5)
        return float(out.stdout.strip())
    except:
        return None

# =========================================================
# FSM LOGIC (UNCHANGED)
# =========================================================
def tes_ahu_simple(T_amb, T_des, T_tank, peak):
    need_heat = T_amb < T_des
    tank_low = T_tank <= 40
    tank_full = T_tank >= 60

    if need_heat:
        if peak:
            return (AHUState.VENT, TESState.DISCHARGE, 1) if not tank_low else (AHUState.NORMAL, TESState.IDLE, 2)
        else:
            return (AHUState.NORMAL, TESState.CHARGING, 3) if not tank_full else (AHUState.NORMAL, TESState.IDLE, 4)
    else:
        if peak:
            return AHUState.IDLE, TESState.IDLE, 5
        else:
            return (AHUState.IDLE, TESState.CHARGING, 6) if not tank_full else (AHUState.IDLE, TESState.IDLE, 7)

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
        with open(LOG_FILE, "w", newline="") as f:
            csv.writer(f).writerow(["timestamp","minute","hour","T_des","T_amb","T_tank","AHU","TES"])

def log_csv(row):
    with open(LOG_FILE, "a", newline="") as f:
        csv.writer(f).writerow(row)

# =========================================================
# MAIN LOOP
# =========================================================
def run_continuous_test():
    setup_gpio()
    initialize_log()

    log_rows = []  # pandas storage

    energy = {k: 0 for k in POWER_RATINGS}
    runtime = {k: 0 for k in POWER_RATINGS}

    try:
        for i, row in enumerate(CONTINUOUS_TEST, 1):
            start = time.time()

            T_des = row["desired_temp"]
            peak = row["peak_state"]

            sensors = read_all_sensors()
            T_amb = read_temp_smtc(5)
            T_tank = sensors["tank_outlet"]

            if T_amb is None or T_tank is None:
                a, t, cid = AHUState.IDLE, TESState.IDLE, -1
                v=b=p=h=False
            else:
                a, t, cid = tes_ahu_simple(T_amb, T_des, T_tank, peak)
                v,b,p,h = actuation_fsm(a,t)

            set_outputs(v,b,p,h)

            # =========================
            # ENERGY + RUNTIME UPDATE
            # =========================
            dt = 1/60

            if p:
                energy["pump"] += POWER_RATINGS["pump"]*dt
                runtime["pump"] += 1
            if h:
                energy["heater"] += POWER_RATINGS["heater"]*dt
                runtime["heater"] += 1
            if b:
                energy["fan"] += POWER_RATINGS["fan"]*dt
                runtime["fan"] += 1
            if v:
                energy["valve"] += POWER_RATINGS["valve"]*dt
                runtime["valve"] += 1

            # =========================
            # STORE ROW (PANDAS)
            # =========================
            row_data = {
                "minute": i,
                "hour": row["sim_hour"],
                "T_des": T_des,
                "T_amb": T_amb,
                "T_tank": T_tank,
                "AHU": a.name,
                "TES": t.name,
                "pump_on": p,
                "heater_on": h,
                "fan_on": b,
                "valve_on": v,
                "energy_pump_Wh": energy["pump"],
                "energy_heater_Wh": energy["heater"],
                "runtime_pump_min": runtime["pump"],
                "runtime_heater_min": runtime["heater"],
            }

            log_rows.append(row_data)

            log_csv([time.time(), i, row["sim_hour"], T_des, T_amb, T_tank, a.name, t.name])

            time.sleep(max(0, MINUTE_DURATION_SEC-(time.time()-start)))

    finally:
        set_outputs(False,False,False,False)
        GPIO.cleanup()

        # =========================
        # SAVE EXCEL
        # =========================
        df = pd.DataFrame(log_rows)
        df.to_excel(EXCEL_FILE, index=False)

        print("\n--- ENERGY (Wh) ---")
        print(energy)

        print("\n--- RUNTIME (min) ---")
        print(runtime)

        print(f"\nExcel saved: {EXCEL_FILE}")

if __name__ == "__main__":
    run_continuous_test()