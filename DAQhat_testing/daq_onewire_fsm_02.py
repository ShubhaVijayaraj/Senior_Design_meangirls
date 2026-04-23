import os
import glob
import csv
import subprocess
import time
from enum import IntEnum
import RPi.GPIO as GPIO

# =========================================================
# 1. LOAD 1-WIRE DRIVERS
# =========================================================
os.system('modprobe w1-gpio')
os.system('modprobe w1-therm')

BASE_DIR = '/sys/bus/w1/devices/'

SENSOR_MAP = {
    "28-xxxxxxxxxxxx": "tank",
}

LOG_FILE = "tes_ahu_log.csv"


# =========================================================
# 2. STATE DEFINITIONS
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
# 3. GPIO PIN DEFINITIONS
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
    return GPIO.HIGH if (command_on == active_high) else GPIO.LOW


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
# 4. SENSOR READING (UPDATED)
# =========================================================
def read_temp(channel):
    try:
        result = subprocess.run(
            ["smtc", "analog", "read", str(channel)],
            capture_output=True,
            text=True,
            timeout=2
        )
        val = result.stdout.strip()
        return float(val) if val else None
    except Exception:
        return None


def get_device_folders():
    return glob.glob(BASE_DIR + '28*')


def read_watertemp(device_file):
    try:
        with open(device_file, 'r') as f:
            lines = f.readlines()

        retry = 0
        while lines[0].strip()[-3:] != 'YES':
            time.sleep(0.2)
            with open(device_file, 'r') as f:
                lines = f.readlines()
            retry += 1
            if retry > 5:
                return None

        equals_pos = lines[1].find('t=')
        if equals_pos != -1:
            return float(lines[1][equals_pos + 2:]) / 1000.0

        return None

    except Exception:
        return None


def read_all_sensors():
    sensor_data = {}
    for folder in get_device_folders():
        device_id = folder.split('/')[-1]
        watertemp = read_watertemp(folder + '/w1_slave')

        if watertemp is not None and device_id in SENSOR_MAP:
            sensor_data[SENSOR_MAP[device_id]] = watertemp

    return sensor_data


def print_detected_sensor_ids():
    print("Detected 1-wire sensor IDs:")
    for folder in get_device_folders():
        print("  ", folder.split('/')[-1])


# =========================================================
# 5. DECISION FSM
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
# 6. ACTUATION FSM
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
        pump_cmd = True
        heater_cmd = True

    elif tes_state == TESState.DISCHARGE:
        valve_cmd = True
        pump_cmd = True
        heater_cmd = False

    blower_cmd = (ahu_state == AHUState.VENT and tes_state == TESState.DISCHARGE)

    return valve_cmd, blower_cmd, pump_cmd, heater_cmd


# =========================================================
# 7. PEAK INPUT
# =========================================================
def read_peak_state():
    return 1


# =========================================================
# 8. CSV LOGGING
# =========================================================
def initialize_log():
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp",
                "thermostat_temp_C",
                "fan_inlet_temp_C",
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


def log_data(*args):
    with open(LOG_FILE, 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([time.strftime("%Y-%m-%d %H:%M:%S")] + list(args))


# =========================================================
# 9. MAIN LOOP (UPDATED SENSOR INPUTS)
# =========================================================
def main():
    setup_gpio()
    initialize_log()
    print_detected_sensor_ids()

    try:
        while True:
            # UPDATED SENSOR INPUT (smtc)
            thermostat_temp = read_temp(5)
            fan_inlet_temp = read_temp(6)

            sensors = read_all_sensors()

            if thermostat_temp is None or fan_inlet_temp is None:
                print("WARNING: Missing analog TC data")
                time.sleep(1)
                continue

            if "tank" not in sensors:
                print("WARNING: Missing tank sensor data")
                print("Sensors found:", sensors)
                time.sleep(1)
                continue

            T_amb = thermostat_temp
            T_tank = sensors["tank"]
            T_des = 25.0
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
            print(f"Thermostat Temp: {thermostat_temp:.2f} C")
            print(f"Fan Inlet Temp:  {fan_inlet_temp:.2f} C")
            print(f"Tank Temp:       {T_tank:.2f} C")
            print(f"Desired Temp:    {T_des:.2f} C")
            print(f"Peak State:      {peak_state}")
            print(f"AHU State:       {ahu_state.name}")
            print(f"TES State:       {tes_state.name}")
            print(f"Case ID:         {case_id}")
            print(f"Commands: V={valve_cmd}, B={blower_cmd}, P={pump_cmd}, H={heater_cmd}")

            log_data(
                thermostat_temp,
                fan_inlet_temp,
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
