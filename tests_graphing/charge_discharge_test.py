# -*- coding: utf-8 -*-
"""
Spyder Editor

This script is meant to charge the water heater to 60 deg C and then discharge
until 40 deg C.

"""
import time
import csv
import subprocess

# =========================================================
# GPIO SAFE FALLBACK (standalone)
# =========================================================
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

        def setmode(self, *args): pass
        def setwarnings(self, *args): pass
        def setup(self, *args): pass
        def output(self, *args): pass
        def cleanup(self): pass

    GPIO = MockGPIO()

# =========================================================
# GPIO PINS
# =========================================================
RELAY_PIN_FAN = 24
RELAY_PIN_PUMP = 17
RELAY_PIN_HEATER = 27

# =========================================================
# FILES
# =========================================================
LOG_FILE = "charge_discharge_test.csv"
SUMMARY_FILE = "charge_discharge_summary.csv"

T_CHARGE_TARGET = 60.0
T_DISCHARGE_TARGET = 40.0
MAX_TEST_TIME = 3600

# =========================================================
# GPIO CONTROL
# =========================================================
def setup_gpio():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    GPIO.setup(RELAY_PIN_FAN, GPIO.OUT)
    GPIO.setup(RELAY_PIN_PUMP, GPIO.OUT)
    GPIO.setup(RELAY_PIN_HEATER, GPIO.OUT)

    set_outputs(False, False, False)

def set_outputs(fan, pump, heater):
    GPIO.output(RELAY_PIN_FAN, GPIO.HIGH if fan else GPIO.LOW)
    GPIO.output(RELAY_PIN_PUMP, GPIO.HIGH if pump else GPIO.LOW)
    GPIO.output(RELAY_PIN_HEATER, GPIO.HIGH if heater else GPIO.LOW)

# =========================================================
# TEMPERATURE INPUT (ONLY ENCLOSURE / TANK VIA SMTC OR SIM)
# =========================================================
def read_temp_smtc(channel=5):
    try:
        result = subprocess.run(
            ["smtc", "analog", "read", str(channel)],
            capture_output=True,
            text=True,
            timeout=3
        )
        return float(result.stdout.strip())
    except:
        return None

# =========================================================
# LOGGING
# =========================================================
def initialize_log():
    with open(LOG_FILE, "w", newline="") as f:
        csv.writer(f).writerow([
            "timestamp",
            "phase",
            "T_amb",
            "T_tank",
            "fan_cmd",
            "pump_cmd",
            "heater_cmd"
        ])

def log_data(phase, T_amb, T_tank, fan, pump, heater):
    with open(LOG_FILE, "a", newline="") as f:
        csv.writer(f).writerow([
            time.strftime("%Y-%m-%d %H:%M:%S"),
            phase,
            T_amb,
            T_tank,
            fan,
            pump,
            heater
        ])

def save_summary(charge_time, discharge_time):
    with open(SUMMARY_FILE, "w", newline="") as f:
        csv.writer(f).writerow(["charge_min", "discharge_min"])
        csv.writer(f).writerow([charge_time / 60, discharge_time / 60])

# =========================================================
# MAIN TEST
# =========================================================
def run_test():
    initialize_log()
    setup_gpio()

    phase = "CHARGING"
    start_time = time.time()

    charge_start = start_time
    discharge_start = None
    stable = 0

    print("Starting charge/discharge test...")

    try:
        while True:
            T_tank = read_temp_smtc(5)
            T_amb = read_temp_smtc(6)

            if T_tank is None:
                continue

            if time.time() - start_time > MAX_TEST_TIME:
                print("Test timed out")
                break

            # =================================================
            # CHARGING
            # =================================================
            if phase == "CHARGING":
                fan = False
                pump = False
                heater = True

                if T_tank >= T_CHARGE_TARGET:
                    stable += 1
                else:
                    stable = 0

                if stable >= 5:
                    charge_time = time.time() - charge_start
                    print(f"Charge complete: {charge_time/60:.2f} min")

                    phase = "DISCHARGE"
                    discharge_start = time.time()
                    stable = 0

            # =================================================
            # DISCHARGING
            # =================================================
            elif phase == "DISCHARGE":
                fan = True
                pump = True
                heater = False

                if T_tank <= T_DISCHARGE_TARGET:
                    stable += 1
                else:
                    stable = 0

                if stable >= 5:
                    discharge_time = time.time() - discharge_start
                    print(f"Discharge complete: {discharge_time/60:.2f} min")

                    save_summary(charge_time, discharge_time)
                    break

            set_outputs(fan, pump, heater)

            log_data(phase, T_amb, T_tank, fan, pump, heater)

            print(f"{phase} | T_tank = {T_tank:.2f} °C")

            time.sleep(1)

    finally:
        set_outputs(False, False, False)
        GPIO.cleanup()
        print("System safely shut down.")

# =========================================================
# RUN
# =========================================================
if __name__ == "__main__":
    run_test()
