# -*- coding: utf-8 -*-
"""
Created on Thu Apr 23 19:16:25 2026

@author: norah

Purpose is to measure change in temperature from HEX inlet and outlet and also
measure time it takes for enclosure temperature to rise 20 deg C.
"""

import time
import csv
import subprocess

# =========================================================
# GPIO (safe standalone fallback)
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
LOG_FILE = "enclosure_only_test.csv"
SUMMARY_FILE = "enclosure_summary.csv"

TEMP_RISE_TARGET = 20.0
MAX_TEST_TIME = 2 * 3600  # 2 hours

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
# ENCLOSURE TEMPERATURE ONLY (SMTC)
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
            "elapsed_s",
            "T_enclosure",
            "fan_cmd",
            "pump_cmd",
            "heater_cmd"
        ])

def log_row(start_time, T, fan, pump, heater):
    with open(LOG_FILE, "a", newline="") as f:
        csv.writer(f).writerow([
            time.strftime("%Y-%m-%d %H:%M:%S"),
            time.time() - start_time,
            T,
            fan,
            pump,
            heater
        ])

def save_summary(rise_time):
    with open(SUMMARY_FILE, "w", newline="") as f:
        csv.writer(f).writerow(["time_to_20C_rise_min"])
        csv.writer(f).writerow([rise_time / 60])

# =========================================================
# MAIN TEST
# =========================================================
def run_test():
    initialize_log()
    setup_gpio()

    start_time = time.time()
    start_temp = None
    stable_count = 0

    print("Running enclosure-only thermal rise test...")

    try:
        while True:
            T = read_temp_smtc(5)

            if T is None:
                continue

            if start_temp is None:
                start_temp = T

            # =========================================
            # FIXED OPERATING MODE (no TES coupling)
            # =========================================
            fan = True
            pump = True
            heater = False   # keep OFF unless you're explicitly heating enclosure

            set_outputs(fan, pump, heater)

            # =========================================
            # 20°C rise detection (stable requirement)
            # =========================================
            if T >= start_temp + TEMP_RISE_TARGET:
                stable_count += 1
            else:
                stable_count = 0

            if stable_count >= 5:
                rise_time = time.time() - start_time
                print(f"20°C rise time: {rise_time/60:.2f} min")
                save_summary(rise_time)
                break

            log_row(start_time, T, fan, pump, heater)

            print(f"T_enclosure = {T:.2f} °C")

            # safety timeout
            if time.time() - start_time > MAX_TEST_TIME:
                print("Test timed out")
                break

            time.sleep(1)

    finally:
        set_outputs(False, False, False)
        GPIO.cleanup()
        print("Test complete and system shut down safely.")

# =========================================================
# RUN
# =========================================================
if __name__ == "__main__":
    run_test()
