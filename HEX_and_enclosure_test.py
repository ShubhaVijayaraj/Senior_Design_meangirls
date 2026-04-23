# -*- coding: utf-8 -*-
"""
Created on Thu Apr 23 19:16:25 2026

@author: norah

Purpose is to measure change in temperature from HEX inlet and outlet and also
measure time it takes for enclosure temperature to rise 20 deg C.
"""

LOG_FILE = "hex_enclosure_test.csv"

def run_hex_enclosure_test():
    initialize_log()
    setup_gpio()

    start_temp = None
    start_time = time.time()

    try:
        while True:
            sensors = read_all_sensors()
            T_amb = read_temp_smtc(5)

            hex_in = sensors.get("hex_inlet")
            hex_out = sensors.get("hex_outlet")

            if start_temp is None and T_amb is not None:
                start_temp = T_amb

            valve_cmd = False
            blower_cmd = True
            pump_cmd = True
            heater_cmd = False

            set_outputs(valve_cmd, blower_cmd, pump_cmd, heater_cmd)

            # Check 20°C rise
            if start_temp and T_amb and (T_amb >= start_temp + 20):
                t_rise = time.time() - start_time
                print(f"20°C rise achieved in {t_rise:.2f} sec")
                break

            log_data(
                T_amb,
                hex_in,
                hex_out,
                valve_cmd,
                blower_cmd,
                pump_cmd,
                heater_cmd
            )

            time.sleep(1)

    finally:
        set_outputs(False, False, False, False)
        GPIO.cleanup()