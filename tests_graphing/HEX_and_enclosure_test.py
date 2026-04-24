# -*- coding: utf-8 -*-
"""
Created on Thu Apr 23 19:16:25 2026

@author: norah

Purpose is to measure change in temperature from HEX inlet and outlet and also
measure time it takes for enclosure temperature to rise 20 deg C.
"""

import time
import csv

LOG_FILE = "hex_enclosure_test.csv"
SUMMARY_FILE = "hex_enclosure_summary.csv"

TEMP_RISE_TARGET = 20.0
MAX_TEST_TIME = 2 * 3600  # 2 hours max

# =========================
# LOGGING
# =========================
def initialize_log():
    with open(LOG_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "timestamp",
            "elapsed_time_s",
            "T_amb",
            "hex_inlet",
            "hex_outlet",
            "blower_cmd",
            "pump_cmd",
            "heater_cmd"
        ])

def log_data(start_time, T_amb, hex_in, hex_out, blower_cmd, pump_cmd, heater_cmd):
    with open(LOG_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            time.strftime("%Y-%m-%d %H:%M:%S"),
            time.time() - start_time,
            T_amb,
            hex_in,
            hex_out,
            blower_cmd,
            pump_cmd,
            heater_cmd
        ])

def save_summary(rise_time):
    with open(SUMMARY_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["time_to_rise_20C_min"])
        writer.writerow([rise_time / 60])

# =========================
# MAIN TEST
# =========================
def run_hex_enclosure_test():
    initialize_log()
    setup_gpio()

    start_temp = None
    start_time = time.time()
    stable_counter = 0

    try:
        while True:
            sensors = read_all_sensors()
            T_amb = read_temp_smtc(5)

            hex_in = sensors.get("hex_inlet")
            hex_out = sensors.get("hex_outlet")

            if T_amb is None:
                continue

            # Initialize start temp
            if start_temp is None:
                start_temp = T_amb

            elapsed_total = time.time() - start_time
            if elapsed_total > MAX_TEST_TIME:
                print("Test timed out")
                break

            # TES DISCHARGE MODE
            blower_cmd = True
            pump_cmd = True
            heater_cmd = False

            set_outputs(False, blower_cmd, pump_cmd, heater_cmd)

            # Check 20°C rise with stability
            if T_amb >= start_temp + TEMP_RISE_TARGET:
                stable_counter += 1
            else:
                stable_counter = 0

            if stable_counter >= 5:
                rise_time = time.time() - start_time
                print(f"20°C rise achieved in {rise_time/60:.2f} min")
                save_summary(rise_time)
                break

            log_data(
                start_time,
                T_amb,
                hex_in,
                hex_out,
                blower_cmd,
                pump_cmd,
                heater_cmd
            )

            print(f"T_amb: {T_amb:.2f} °C | HEX ΔT: {(hex_out - hex_in) if hex_in and hex_out else None}")

            time.sleep(1)

    finally:
        set_outputs(False, False, False, False)
        GPIO.cleanup()
        print("Test complete. System safe.")

# =========================
# RUN
# =========================
if __name__ == "__main__":
    run_hex_enclosure_test()
