# -*- coding: utf-8 -*-
"""
Spyder Editor

This script is meant to charge the water heater to 60 deg C and then discharge
until 40 deg C.

"""
import time
import csv

LOG_FILE = "charge_discharge_test.csv"

T_CHARGE_TARGET = 60.0
T_DISCHARGE_TARGET = 40.0

def run_charge_discharge_test():
    initialize_log()
    setup_gpio()

    phase = "CHARGING"
    start_time = time.time()
    charge_start = start_time
    discharge_start = None

    try:
        while True:
            sensors = read_all_sensors()
            T_tank = sensors.get("tank_outlet")
            T_amb = read_temp_smtc(5)

            if T_tank is None:
                set_outputs(False, False, False, False)
                continue

            # =========================
            # PHASE CONTROL
            # =========================
            if phase == "CHARGING":
                valve_cmd = False
                blower_cmd = False
                pump_cmd = False
                heater_cmd = True

                if T_tank >= T_CHARGE_TARGET:
                    charge_time = time.time() - charge_start
                    print(f"Charge complete in {charge_time/60:.2f} min")
                    phase = "DISCHARGE"
                    discharge_start = time.time()

            elif phase == "DISCHARGE":
                valve_cmd = False
                blower_cmd = True
                pump_cmd = True
                heater_cmd = False

                if T_tank <= T_DISCHARGE_TARGET:
                    discharge_time = time.time() - discharge_start
                    print(f"Discharge complete in {discharge_time/60:.2f} min")
                    break

            set_outputs(valve_cmd, blower_cmd, pump_cmd, heater_cmd)

            log_data(
                phase,
                T_amb,
                T_tank,
                valve_cmd,
                blower_cmd,
                pump_cmd,
                heater_cmd
            )

            time.sleep(1)

    finally:
        set_outputs(False, False, False, False)
        GPIO.cleanup()
