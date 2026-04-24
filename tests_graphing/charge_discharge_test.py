# -*- coding: utf-8 -*-
"""
Spyder Editor

This script is meant to charge the water heater to 60 deg C and then discharge
until 40 deg C.

"""
import time
import csv

LOG_FILE = "charge_discharge_test.csv"
SUMMARY_FILE = "charge_discharge_summary.csv"

T_CHARGE_TARGET = 60.0
T_DISCHARGE_TARGET = 40.0

MAX_TEST_TIME = 1 * 3600  # 1 hiour safety limit

# =========================
# LOGGING
# =========================
def initialize_log():
    with open(LOG_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "timestamp",
            "phase",
            "T_amb",
            "T_tank",
            "blower_cmd",
            "pump_cmd",
            "heater_cmd"
        ])

def log_data(phase, T_amb, T_tank, blower_cmd, pump_cmd, heater_cmd):
    with open(LOG_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            time.strftime("%Y-%m-%d %H:%M:%S"),
            phase,
            T_amb,
            T_tank,
            blower_cmd,
            pump_cmd,
            heater_cmd
        ])

def save_summary(charge_time, discharge_time):
    with open(SUMMARY_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["charge_time_min", "discharge_time_min"])
        writer.writerow([charge_time / 60, discharge_time / 60])

# =========================
# MAIN TEST
# =========================
def run_charge_discharge_test():
    initialize_log()
    setup_gpio()

    phase = "CHARGING"
    start_time = time.time()

    charge_start = start_time
    discharge_start = None

    stable_counter = 0  # avoids noise switching

    try:
        while True:
            sensors = read_all_sensors()
            T_tank = sensors.get("tank_outlet")
            T_amb = read_temp_smtc(5)

            if T_tank is None:
                set_outputs(False, False, False, False)
                continue

            elapsed_total = time.time() - start_time
            if elapsed_total > MAX_TEST_TIME:
                print("Test timed out")
                break

            # =========================
            # CHARGING PHASE
            # =========================
            if phase == "CHARGING":
                blower_cmd = False
                pump_cmd = False
                heater_cmd = True

                if T_tank >= T_CHARGE_TARGET:
                    stable_counter += 1
                else:
                    stable_counter = 0

                # Require 5 consecutive seconds above target
                if stable_counter >= 5:
                    charge_time = time.time() - charge_start
                    print(f"Charge complete: {charge_time/60:.2f} min")

                    phase = "DISCHARGE"
                    discharge_start = time.time()
                    stable_counter = 0

            # =========================
            # DISCHARGE PHASE
            # =========================
            elif phase == "DISCHARGE":
                blower_cmd = True
                pump_cmd = True
                heater_cmd = False

                if T_tank <= T_DISCHARGE_TARGET:
                    stable_counter += 1
                else:
                    stable_counter = 0

                if stable_counter >= 5:
                    discharge_time = time.time() - discharge_start
                    print(f"Discharge complete: {discharge_time/60:.2f} min")

                    save_summary(charge_time, discharge_time)
                    break

            # Apply outputs
            set_outputs(False, blower_cmd, pump_cmd, heater_cmd)

            # Log data
            log_data(
                phase,
                T_amb,
                T_tank,
                blower_cmd,
                pump_cmd,
                heater_cmd
            )

            print(f"{phase} | Tank: {T_tank:.2f} °C")

            time.sleep(1)

    finally:
        set_outputs(False, False, False, False)
        GPIO.cleanup()
        print("Test complete. System safe.")

# =========================
# RUN
# =========================
if __name__ == "__main__":
    run_charge_discharge_test()
