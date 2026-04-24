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

print("GPIO AVAILABLE:", GPIO_AVAILABLE)
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

    def setmode(self, mode):
        print("[MOCK GPIO] setmode:", mode)

    def setwarnings(self, flag):
        pass

    def setup(self, pin, mode):
        print(f"[MOCK GPIO] setup pin {pin}")

    def output(self, pin, value):
        print(f"[MOCK GPIO] pin {pin} -> {value}")

    def cleanup(self):
        print("[MOCK GPIO] cleanup")

# =========================================================
# GPIO PINS
# =========================================================
RELAY_PIN_FAN = 24
RELAY_PIN_PUMP = 17
RELAY_PIN_HEATER = 27

# =========================================================
# FILES
# =========================================================
LOG_FILE = "enclosure_hex_test.csv"
SUMMARY_FILE = "enclosure_summary.csv"

TEMP_RISE_TARGET = 20.0
MAX_TEST_TIME = 2 * 3600  # safety limit

ASSUMED_AMBIENT = 21.0  # optional reference

# =========================================================
# GPIO CONTROL
# =========================================================
def set_outputs(fan, pump, heater):
    GPIO.output(RELAY_PIN_FAN, GPIO.HIGH if fan else GPIO.LOW)
    GPIO.output(RELAY_PIN_PUMP, GPIO.HIGH if pump else GPIO.LOW)
    GPIO.output(RELAY_PIN_HEATER, GPIO.HIGH if heater else GPIO.LOW)

def setup_gpio():
    if GPIO_AVAILABLE:
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)

        GPIO.setup(RELAY_PIN_FAN, GPIO.OUT)
        GPIO.setup(RELAY_PIN_PUMP, GPIO.OUT)
        GPIO.setup(RELAY_PIN_HEATER, GPIO.OUT)

    set_outputs(False, False, False)
    
def shutdown_all():
    try:
        set_outputs(False, False, False)
    except:
        pass

    try:
        GPIO.cleanup()
    except:
        pass

# =========================================================
# SMTC READ (THERMOCOUPLES)
# =========================================================
def read_temp_smtc(channel):
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
            "T_enclosure_CH5",
            "T_hex_front_CH6",
            "HEX_inlet",
            "HEX_outlet",
            "HEX_deltaT",
            "fan",
            "pump",
            "heater"
        ])

def log_row(start_time, T5, T6, hex_in, hex_out, fan, pump, heater):
    deltaT = None
    if hex_in is not None and hex_out is not None:
        deltaT = hex_out - hex_in

    with open(LOG_FILE, "a", newline="") as f:
        csv.writer(f).writerow([
            time.strftime("%Y-%m-%d %H:%M:%S"),
            time.time() - start_time,
            T5,
            T6,
            hex_in,
            hex_out,
            deltaT,
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

    print("Starting enclosure + HEX thermal test...")

    try:
        while True:
            # =================================================
            # TEMPERATURE READINGS
            # =================================================
            T5 = read_temp_smtc(5)  # enclosure
            T6 = read_temp_smtc(6)  # in front of HEX

            # If either fails, skip iteration
            if T5 is None:
                continue

            if start_temp is None:
                start_temp = T5

            # Optional HEX temps (if you still have sensors)
            hex_in = None
            hex_out = None

            # =================================================
            # OPERATING MODE (fan + pump only)
            # =================================================
            fan = True
            pump = True
            heater = False

            set_outputs(fan, pump, heater)

            # =================================================
            # ENCLOSURE RISE CONDITION (20°C)
            # =================================================
            if T5 >= start_temp + TEMP_RISE_TARGET:
                stable_count += 1
            else:
                stable_count = 0

            if stable_count >= 5:
                rise_time = time.time() - start_time
                print(f"20°C rise time: {rise_time/60:.2f} min")
                save_summary(rise_time)
                break

            # =================================================
            # LOG DATA
            # =================================================
            log_row(start_time, T5, T6, hex_in, hex_out, fan, pump, heater)

            print(f"Enclosure (CH5): {T5:.2f} °C | HEX front (CH6): {T6:.2f} °C")

            # safety timeout
            if time.time() - start_time > MAX_TEST_TIME:
                print("Test timed out")
                break

            time.sleep(1)

    finally:
        shutdown_all()
        print("All systems OFF. GPIO cleaned up.")

# =========================================================
# RUN
# =========================================================
if __name__ == "__main__":
    run_test()
