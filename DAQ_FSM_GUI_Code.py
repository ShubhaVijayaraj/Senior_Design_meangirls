import os
import glob
import csv
import time
from enum import IntEnum
import RPi.GPIO as GPIO

# =========================================================
# 1. LOAD 1-WIRE DRIVERS
# =========================================================
os.system('modprobe w1-gpio')
os.system('modprobe w1-therm')

BASE_DIR = '/sys/bus/w1/devices/'

# Replace these with your real sensor IDs
SENSOR_MAP = {
    "28-xxxxxxxxxxxx": "room",
    "28-yyyyyyyyyyyy": "tank",
}

LOG_FILE = "tes_ahu_log.csv"


# 2. STATE DEFINITIONS
class AHUState(IntEnum):
    IDLE = 0
    NORMAL = 1
    VENT = 2


class TESState(IntEnum):
    IDLE = 0
    CHARGING = 1
    DISCHARGE = 2


# 3. GPIO PIN DEFINITIONS
RELAY_PIN_SOLENOID = 23
RELAY_PIN_FAN = 24
RELAY_PIN_PUMP = 17
RELAY_PIN_HEATER = 27

ACTIVE_HIGH = {
    "solenoid": False,   # active LOW relay
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



# 4. 1-WIRE SENSOR READING
def get_device_folders():
    return glob.glob(BASE_DIR + '28*')


def read_temp(device_file):
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
            temp_c = float(lines[1][equals_pos + 2:]) / 1000.0
            return temp_c

        return None

    except Exception:
        return None


def read_all_sensors():
    sensor_data = {}
    device_folders = get_device_folders()

    for folder in device_folders:
        device_id = folder.split('/')[-1]
        temp = read_temp(folder + '/w1_slave')

        if temp is not None and device_id in SENSOR_MAP:
            sensor_data[SENSOR_MAP[device_id]] = temp

    return sensor_data


def print_detected_sensor_ids():
    print("Detected 1-wire sensor IDs:")
    for folder in get_device_folders():
        print("  ", folder.split('/')[-1])


# 5. DECISION FSM
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



# 6. ACTUATION FSM
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
        pump_cmd = True      # circulate while heating
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


# 7. OTHER INPUTS

def read_desired_temperature():
    # replace later with thermostat/UI/setpoint input
    return 25.0


def read_peak_state():
    # replace later with your schedule logic
    return 1



# 8. CSV LOGGING

def initialize_log():
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, mode='w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp",
                "T_amb_C",
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


def log_data(T_amb, T_des, T_tank, peak_state, ahu_state, tes_state, case_id,
             valve_cmd, blower_cmd, pump_cmd, heater_cmd):
    with open(LOG_FILE, mode='a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            time.strftime("%Y-%m-%d %H:%M:%S"),
            T_amb,
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


# 9. MAIN LOOP

def main():
    setup_gpio()
    initialize_log()
    print_detected_sensor_ids()

    try:
        while True:
            sensors = read_all_sensors()

            if "room" not in sensors or "tank" not in sensors:
                print("WARNING: Missing sensor data")
                print("Sensors found:", sensors)
                time.sleep(1)
                continue

            # Inputs
            T_amb = sensors["room"]
            T_tank = sensors["tank"]
            T_des = read_desired_temperature()
            peak_state = read_peak_state()

            # Decision FSM
            ahu_state, tes_state, case_id = tes_ahu_simple(
                T_amb, T_des, T_tank, peak_state
            )

            # Actuation FSM
            valve_cmd, blower_cmd, pump_cmd, heater_cmd = actuation_fsm(
                ahu_state, tes_state
            )

            # Safety cutoff
            if T_tank > 70.0:
                heater_cmd = False

            # Output to relays
            set_outputs(valve_cmd, blower_cmd, pump_cmd, heater_cmd)

            # Print live data
            print("------------------------------------------------")
            print(f"T_amb={T_amb:.2f} C, T_des={T_des:.2f} C, T_tank={T_tank:.2f} C, Peak={peak_state}")
            print(f"AHU State={ahu_state.name}, TES State={tes_state.name}, Case ID={case_id}")
            print(f"Valve={valve_cmd}, Blower={blower_cmd}, Pump={pump_cmd}, Heater={heater_cmd}")

            # Save to CSV
            log_data(
                T_amb, T_des, T_tank, peak_state,
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


