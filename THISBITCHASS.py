import os
import glob
import csv
import time
import subprocess
from enum import IntEnum
import RPi.GPIO as GPIO

# =========================================================
# 1. LOAD 1-WIRE DRIVERS
# =========================================================
os.system("modprobe w1-gpio")
os.system("modprobe w1-therm")

BASE_DIR = "/sys/bus/w1/devices/"
LOG_FILE = "tes_ahu_log.csv"

# =========================================================
# 2. 1-WIRE SENSOR MAP
# PUT THE REAL FULL 1-WIRE IDS HERE
# wh_outlet MUST BE THE WATER HEATER OUTLET SENSOR
# the one ending in 37009c
# =========================================================
SENSOR_MAP = {
    "28-aaaaaaaaaaaa": "wh_inlet",      # water heater inlet
    "28-00000037009c": "wh_outlet",     # water heater outlet  <-- T_tank comes from this
    "28-cccccccccccc": "hex_inlet",     # heat exchanger inlet
    "28-dddddddddddd": "hex_outlet",    # heat exchanger outlet
}

# =========================================================
# 3. STATE DEFINITIONS
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
# 4. GPIO PIN DEFINITIONS
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


def set_outputs(valve_cmd: bool, blower_cmd: bool, pump_cmd: bool, heater_cmd: bool):
    GPIO.output(RELAY_PIN_SOLENOID, relay_level("solenoid", valve_cmd))
    GPIO.output(RELAY_PIN_FAN, relay_level("fan", blower_cmd))
    GPIO.output(RELAY_PIN_PUMP, relay_level("pump", pump_cmd))
    GPIO.output(RELAY_PIN_HEATER, relay_level("heater", heater_cmd))


# =========================================================
# 5. 1-WIRE SENSOR READING
# =========================================================
def get_device_folders():
    return glob.glob(BASE_DIR + "28*")


def read_temp_1wire(device_file):
    try:
        with open(device_file, "r") as f:
            lines = f.readlines()

        retry = 0
        while lines[0].strip()[-3:] != "YES":
            time.sleep(0.2)
            with open(device_file, "r") as f:
                lines = f.readlines()
            retry += 1
            if retry > 5:
                return None

        equals_pos = lines[1].find("t=")
        if equals_pos != -1:
            temp_c = float(lines[1][equals_pos + 2:]) / 1000.0
            return temp_c

        return None

    except Exception:
        return None


def read_all_1wire_sensors():
    sensor_data = {}
    device_folders = get_device_folders()

    for folder in device_folders:
        device_id = folder.split("/")[-1]
        temp = read_temp_1wire(folder + "/w1_slave")

        if temp is not None and device_id in SENSOR_MAP:
            sensor_name = SENSOR_MAP[device_id]
            sensor_data[sensor_name] = temp

    return sensor_data


def print_detected_sensor_ids():
    print("Detected 1-wire sensor IDs:")
    for folder in get_device_folders():
        print("  ", folder.split("/")[-1])


# =========================================================
# 6. SMTC ANALOG TEMP READING
# =========================================================
def read_temp_smtc(channel):
    try:
        result = subprocess.run(
            ["smtc", "analog", "read", str(channel)],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode != 0:
            return None

        return float(result.stdout.strip())

    except Exception:
        return None


# =========================================================
# 7. DECISION FSM
# =========================================================
def tes_ahu_simple(T_amb: float, T_des: float, T_tank: float, peak_state: int):
    T_full = 60.0
    T_low = 40.0

    need_heat = T_amb < T_des
    tank_low = T_tank <= T_low
    tank_full = T_tank >= T_full

    ahu_state = AHUState.IDLE
    tes_state = TESState.IDLE
    case_id = 0

    if need_heat:
        if peak_state == 1:
            if not tank_low:
                ahu_state = AHUState.VENT
                tes_state = TESState.DISCHARGE
                case_id = 1
            else:
                ahu_state = AHUState.NORMAL
                tes_state = TESState.IDLE
                case_id = 2
        else:
            if not tank_full:
                ahu_state = AHUState.NORMAL
                tes_state = TESState.CHARGING
                case_id = 3
            else:
                ahu_state = AHUState.NORMAL
                tes_state = TESState.IDLE
                case_id = 4
    else:
        if peak_state == 1:
            ahu_state = AHUState.IDLE
            tes_state = TESState.IDLE
            case_id = 5
        else:
            if not tank_full:
                ahu_state = AHUState.IDLE
                tes_state = TESState.CHARGING
                case_id = 6
            else:
                ahu_state = AHUState.IDLE
                tes_state = TESState.IDLE
                case_id = 7

    return ahu_state, tes_state, case_id


# =========================================================
# 8. ACTUATION FSM
# =========================================================
def actuation_fsm(ahu_state: AHUState, tes_state: TESState):
    valve_cmd = False
    blower_cmd = False
    pump_cmd = False
    heater_cmd = False

    if tes_state == TESState.IDLE:
        valve_cmd = False
        pump_cmd = False
        heater_cmd = False

    elif tes_state == TESState.CHARGING:
        valve_cmd = False
        pump_cmd = False
        heater_cmd = True

    elif tes_state == TESState.DISCHARGE:
        valve_cmd = True
        pump_cmd = True
        heater_cmd = False

    if ahu_state == AHUState.VENT and tes_state == TESState.DISCHARGE:
        blower_cmd = True
    else:
        blower_cmd = False

    return valve_cmd, blower_cmd, pump_cmd, heater_cmd


# =========================================================
# 9. OTHER INPUTS
# =========================================================
def read_desired_temperature():
    return 25.0


def read_peak_state():
    return 1


# =========================================================
# 10. CSV LOGGING
# =========================================================
def initialize_log():
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, mode="w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp",
                "T_amb_ch5_C",
                "T_amb_ch6_C",
                "T_amb_avg_C",
                "wh_inlet_C",
                "wh_outlet_C",
                "hex_inlet_C",
                "hex_outlet_C",
                "T_des_C",
                "T_tank_C",
                "peak_state",
                "ahu_state",
                "tes_state",
                "case_id",
                "valve_cmd",
                "blower_cmd",
                "pump_cmd",
                "heater_cmd"
            ])


def log_data(
    T_amb_5, T_amb_6, T_amb_avg,
    wh_inlet, wh_outlet, hex_inlet, hex_outlet,
    T_des, T_tank, peak_state,
    ahu_state, tes_state, case_id,
    valve_cmd, blower_cmd, pump_cmd, heater_cmd
):
    with open(LOG_FILE, mode="a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            time.strftime("%Y-%m-%d %H:%M:%S"),
            T_amb_5,
            T_amb_6,
            T_amb_avg,
            wh_inlet,
            wh_outlet,
            hex_inlet,
            hex_outlet,
            T_des,
            T_tank,
            peak_state,
            ahu_state.name,
            tes_state.name,
            case_id,
            valve_cmd,
            blower_cmd,
            pump_cmd,
            heater_cmd
        ])


# =========================================================
# 11. MAIN LOOP
# =========================================================
def main():
    setup_gpio()
    initialize_log()
    print_detected_sensor_ids()

    try:
        while True:
            T_amb_5 = read_temp_smtc(5)
            T_amb_6 = read_temp_smtc(6)

            sensor_data = read_all_1wire_sensors()

            wh_inlet = sensor_data.get("wh_inlet")
            wh_outlet = sensor_data.get("wh_outlet")
            hex_inlet = sensor_data.get("hex_inlet")
            hex_outlet = sensor_data.get("hex_outlet")

            if T_amb_5 is None or T_amb_6 is None:
                print("WARNING: Missing analog TC data on channels 5 and/or 6")
                time.sleep(1)
                continue

            if wh_inlet is None or wh_outlet is None or hex_inlet is None or hex_outlet is None:
                print("WARNING: Missing one or more 1-wire water temperature readings")
                print(f"wh_inlet={wh_inlet}, wh_outlet={wh_outlet}, hex_inlet={hex_inlet}, hex_outlet={hex_outlet}")
                time.sleep(1)
                continue

            T_amb = (T_amb_5 + T_amb_6) / 2.0

            # T_tank comes from 1-wire water heater outlet
            T_tank = wh_outlet

            T_des = read_desired_temperature()
            peak_state = read_peak_state()

            ahu_state, tes_state, case_id = tes_ahu_simple(
                T_amb, T_des, T_tank, peak_state
            )

            valve_cmd, blower_cmd, pump_cmd, heater_cmd = actuation_fsm(
                ahu_state, tes_state
            )

            if T_tank > 70.0:
                heater_cmd = False

            set_outputs(valve_cmd, blower_cmd, pump_cmd, heater_cmd)

            print("------------------------------------------------")
            print(f"Ambient CH5 = {T_amb_5:.2f} C")
            print(f"Ambient CH6 = {T_amb_6:.2f} C")
            print(f"Ambient AVG = {T_amb:.2f} C")
            print(f"WH Inlet    = {wh_inlet:.2f} C")
            print(f"WH Outlet   = {wh_outlet:.2f} C")
            print(f"HEX Inlet   = {hex_inlet:.2f} C")
            print(f"HEX Outlet  = {hex_outlet:.2f} C")
            print(f"T_des       = {T_des:.2f} C")
            print(f"T_tank(FSM) = {T_tank:.2f} C")
            print(f"Peak        = {peak_state}")
            print(f"AHU State   = {ahu_state.name}")
            print(f"TES State   = {tes_state.name}")
            print(f"Case ID     = {case_id}")
            print(f"Valve={valve_cmd}, Blower={blower_cmd}, Pump={pump_cmd}, Heater={heater_cmd}")

            log_data(
                T_amb_5, T_amb_6, T_amb,
                wh_inlet, wh_outlet, hex_inlet, hex_outlet,
                T_des, T_tank, peak_state,
                ahu_state, tes_state, case_id,
                valve_cmd, blower_cmd, pump_cmd, heater_cmd
            )

            time.sleep(2)

    except KeyboardInterrupt:
        print("Program stopped by user.")

    finally:
        set_outputs(False, False, False, False)
        GPIO.cleanup()
        print("All relays OFF. GPIO cleaned up.")


if __name__ == "__main__":
    main()