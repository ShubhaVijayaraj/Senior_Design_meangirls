import os
import glob
import csv
import time
import subprocess
from enum import IntEnum

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

        def setmode(self, *args, **kwargs):
            pass

        def setwarnings(self, *args, **kwargs):
            pass

        def setup(self, *args, **kwargs):
            pass

        def output(self, *args, **kwargs):
            pass

        def cleanup(self, *args, **kwargs):
            pass

    GPIO = MockGPIO()

# =========================================================
# 1. LOAD 1-WIRE DRIVERS
# =========================================================
os.system("modprobe w1-gpio")
os.system("modprobe w1-therm")

BASE_DIR = "/sys/bus/w1/devices/"
LOG_FILE = "continuous_test_log_20sec_deadband.csv"

# =========================================================
# 2. CONTINUOUS TEST MATRIX
#    1 real minute = 1 simulated hour
# =========================================================
CONTINUOUS_TEST = [
    {"sim_hour": 0,  "peak_state": 0, "desired_temp": 21},
    {"sim_hour": 1,  "peak_state": 0, "desired_temp": 21},
    {"sim_hour": 2,  "peak_state": 0, "desired_temp": 21},
    {"sim_hour": 3,  "peak_state": 0, "desired_temp": 21},
    {"sim_hour": 4,  "peak_state": 0, "desired_temp": 21},
    {"sim_hour": 5,  "peak_state": 0, "desired_temp": 24},
    {"sim_hour": 6,  "peak_state": 0, "desired_temp": 24},
    {"sim_hour": 7,  "peak_state": 0, "desired_temp": 24},
    {"sim_hour": 8,  "peak_state": 0, "desired_temp": 24},
    {"sim_hour": 9,  "peak_state": 0, "desired_temp": 24},
    {"sim_hour": 10, "peak_state": 0, "desired_temp": 24},
    {"sim_hour": 11, "peak_state": 0, "desired_temp": 24},
    {"sim_hour": 12, "peak_state": 0, "desired_temp": 24},
    {"sim_hour": 13, "peak_state": 0, "desired_temp": 24},
    {"sim_hour": 14, "peak_state": 0, "desired_temp": 27},
    {"sim_hour": 15, "peak_state": 0, "desired_temp": 27},
    {"sim_hour": 16, "peak_state": 1, "desired_temp": 27},
    {"sim_hour": 17, "peak_state": 1, "desired_temp": 27},
    {"sim_hour": 18, "peak_state": 1, "desired_temp": 27},
    {"sim_hour": 19, "peak_state": 1, "desired_temp": 27},
    {"sim_hour": 20, "peak_state": 1, "desired_temp": 22},
    {"sim_hour": 21, "peak_state": 0, "desired_temp": 22},
    {"sim_hour": 22, "peak_state": 0, "desired_temp": 22},
    {"sim_hour": 23, "peak_state": 0, "desired_temp": 22},
]

MINUTE_DURATION_SEC = 60
SAMPLE_INTERVAL_SEC = 20
SAMPLES_PER_SIM_HOUR = MINUTE_DURATION_SEC // SAMPLE_INTERVAL_SEC
DEADBAND_C = 1.0

# =========================================================
# 3. 1-WIRE SENSOR MAP
#    Real sensor IDs from your system.
# =========================================================
SENSOR_MAP = {
    "28-00000034c7d5": "hex_inlet",     # inlet of HEX
    "28-00000037e0c4": "hex_outlet",    # outlet of HEX
    "28-00000037009c": "tank_outlet",   # outlet of water heater
    "28-0000005b080d": "tank_inlet",    # inlet of water heater
}

# =========================================================
# 4. STATE DEFINITIONS
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
# 5. GPIO PIN DEFINITIONS
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
# 6. 1-WIRE SENSOR READING
# =========================================================
def get_device_folders():
    return glob.glob(BASE_DIR + "28*")

def read_temp(device_file):
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
            return float(lines[1][equals_pos + 2:]) / 1000.0

        return None
    except:
        return None

def read_all_sensors():
    sensor_data = {
        "tank_inlet": None,
        "tank_outlet": None,
        "hex_inlet": None,
        "hex_outlet": None,
    }

    for folder in get_device_folders():
        device_id = folder.split("/")[-1]
        temp = read_temp(folder + "/w1_slave")

        if temp is not None and device_id in SENSOR_MAP:
            sensor_name = SENSOR_MAP[device_id]
            sensor_data[sensor_name] = temp

    return sensor_data

def print_detected_sensor_ids():
    print("Detected 1-wire sensor IDs:")
    folders = get_device_folders()
    if not folders:
        print("  No 1-wire sensors detected.")
    for folder in folders:
        print("  ", folder.split("/")[-1])

# =========================================================
# 7. DAQ (SMTC)
# =========================================================
def read_temp_smtc(channel):
    try:
        result = subprocess.run(
            ["smtc", "analog", "read", str(channel)],
            capture_output=True,
            text=True,
            timeout=5
        )
        return float(result.stdout.strip())
    except:
        return None

# =========================================================
# 8. DECISION FSM
#    SAME STATE/CASE LOGIC, WITH DEADBAND ONLY APPLIED TO HEAT DEMAND
# =========================================================
def tes_ahu_simple(T_amb: float, T_des: float, T_tank: float, peak_state: int):
    T_full = 60.0
    T_low = 35.0

    # Deadband: do not call for heat unless enclosure temp is more than
    # DEADBAND_C below the desired temperature.
    need_heat = T_amb < (T_des - DEADBAND_C)
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
# 9. ACTUATION FSM
#    LOGIC KEPT EXACTLY THE SAME
# =========================================================
def actuation_fsm(ahu_state: AHUState, tes_state: TESState):
    valve_cmd = False
    blower_cmd = False
    pump_cmd = False
    heater_cmd = False

    if tes_state == TESState.CHARGING:
        pump_cmd = False
        heater_cmd = True
        blower_cmd = True

    elif tes_state == TESState.DISCHARGE:
        valve_cmd = True
        pump_cmd = True
        blower_cmd = True

    if ahu_state == AHUState.VENT and tes_state == TESState.DISCHARGE:
        blower_cmd = True

    return valve_cmd, blower_cmd, pump_cmd, heater_cmd

# =========================================================
# 10. LOGGING
# =========================================================
def initialize_log():
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, mode="w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp",
                "minute_index",
                "sample_index",
                "elapsed_test_time_sec",
                "sim_hour",
                "sim_minute",
                "peak_state",
                "desired_temp_C",
                "enclosure_temp_C",
                "enclosure_temp_ch6_C",
                "tank_inlet_C",
                "tank_outlet_C",
                "hex_inlet_C",
                "hex_outlet_C",
                "t_tank_used_by_fsm_C",
                "ahu_state",
                "tes_state",
                "case_id",
                "valve_cmd",
                "blower_cmd",
                "pump_cmd",
                "heater_cmd",
                "state_key",
                "valve_on_time_in_state_sec",
                "blower_on_time_in_state_sec",
                "pump_on_time_in_state_sec",
                "heater_on_time_in_state_sec",
            ])

def log_data(*row):
    with open(LOG_FILE, mode="a", newline="") as f:
        csv.writer(f).writerow([
            time.strftime("%Y-%m-%d %H:%M:%S"),
            *row
        ])

# =========================================================
# 11. MAIN TEST LOOP
# =========================================================
def fmt_temp(value):
    if value is None:
        return "None"
    return f"{value:.2f} °C"

def make_state_key(ahu_state, tes_state, case_id):
    return f"AHU_{ahu_state.name}__TES_{tes_state.name}__CASE_{case_id}"

def blank_component_times():
    return {
        "valve": 0.0,
        "blower": 0.0,
        "pump": 0.0,
        "heater": 0.0,
    }

def add_component_on_time(component_times, state_key, valve_cmd, blower_cmd, pump_cmd, heater_cmd, dt_sec):
    if state_key not in component_times:
        component_times[state_key] = blank_component_times()

    if valve_cmd:
        component_times[state_key]["valve"] += dt_sec
    if blower_cmd:
        component_times[state_key]["blower"] += dt_sec
    if pump_cmd:
        component_times[state_key]["pump"] += dt_sec
    if heater_cmd:
        component_times[state_key]["heater"] += dt_sec

def print_component_times_for_state(component_times, state_key):
    times = component_times.get(state_key, blank_component_times())
    print("--- COMPONENT ON TIME IN THIS STATE SO FAR ---")
    print(f"State Key:               {state_key}")
    print(f"Valve On Time:           {times['valve']:.0f} sec")
    print(f"Blower On Time:          {times['blower']:.0f} sec")
    print(f"Pump On Time:            {times['pump']:.0f} sec")
    print(f"Heater On Time:          {times['heater']:.0f} sec")
    print("")

def print_total_component_times(component_times):
    total = blank_component_times()
    for state_times in component_times.values():
        for component in total:
            total[component] += state_times[component]

    print("--- TOTAL COMPONENT ON TIME THIS TEST ---")
    print(f"Valve Total:             {total['valve']:.0f} sec")
    print(f"Blower Total:            {total['blower']:.0f} sec")
    print(f"Pump Total:              {total['pump']:.0f} sec")
    print(f"Heater Total:            {total['heater']:.0f} sec")
    print("")

def run_continuous_test():
    print_detected_sensor_ids()
    initialize_log()
    setup_gpio()

    total_samples = len(CONTINUOUS_TEST) * SAMPLES_PER_SIM_HOUR
    component_times_by_state = {}

    print("\nStarting 24-minute continuous test...")
    print("1 real minute = 1 simulated hour")
    print(f"Sample rate: every {SAMPLE_INTERVAL_SEC} seconds")
    print(f"Samples per simulated hour: {SAMPLES_PER_SIM_HOUR}")
    print(f"Deadband: +/- {DEADBAND_C:.1f} °C around desired temp")
    print(f"Total run time: {len(CONTINUOUS_TEST)} minutes")
    print(f"Total samples: {total_samples}\n")

    sample_counter = 0

    try:
        for minute_index, row in enumerate(CONTINUOUS_TEST, start=1):
            sim_hour = row["sim_hour"]
            peak_state = row["peak_state"]
            T_des = row["desired_temp"]

            minute_start_time = time.time()

            for sample_index in range(1, SAMPLES_PER_SIM_HOUR + 1):
                sample_start_time = time.time()
                sample_counter += 1

                elapsed_test_time_sec = ((minute_index - 1) * MINUTE_DURATION_SEC) + ((sample_index - 1) * SAMPLE_INTERVAL_SEC)
                sim_minute = (sample_index - 1) * 20

                sensors = read_all_sensors()
                enclosure_temp = read_temp_smtc(5)      # main enclosure temperature used by FSM
                enclosure_temp_ch6 = read_temp_smtc(6)  # extra DAQ reading for display/logging

                tank_inlet = sensors.get("tank_inlet")
                tank_outlet = sensors.get("tank_outlet")
                hex_inlet = sensors.get("hex_inlet")
                hex_outlet = sensors.get("hex_outlet")

                # Keep the FSM input source aligned with your current code logic:
                T_amb = enclosure_temp
                T_tank = tank_outlet

                if T_amb is None or T_tank is None:
                    ahu_state = AHUState.IDLE
                    tes_state = TESState.IDLE
                    case_id = -1
                    valve_cmd = False
                    blower_cmd = False
                    pump_cmd = False
                    heater_cmd = False
                    set_outputs(False, False, False, False)
                else:
                    ahu_state, tes_state, case_id = tes_ahu_simple(T_amb, T_des, T_tank, peak_state)
                    valve_cmd, blower_cmd, pump_cmd, heater_cmd = actuation_fsm(ahu_state, tes_state)

                    if T_tank > 70.0:
                        heater_cmd = False

                    set_outputs(valve_cmd, blower_cmd, pump_cmd, heater_cmd)

                state_key = make_state_key(ahu_state, tes_state, case_id)
                add_component_on_time(
                    component_times_by_state,
                    state_key,
                    valve_cmd,
                    blower_cmd,
                    pump_cmd,
                    heater_cmd,
                    SAMPLE_INTERVAL_SEC,
                )

                state_times = component_times_by_state[state_key]

                print("============================================================")
                print(f"SAMPLE {sample_counter:02d} / {total_samples}")
                print(f"MINUTE {minute_index:02d} / {len(CONTINUOUS_TEST)}")
                print(f"Simulated Time:         {sim_hour:02d}:{sim_minute:02d}")
                print(f"Real Elapsed Time:      {elapsed_test_time_sec} sec")
                print(f"Peak State:             {peak_state}")
                print(f"Desired Temp:           {T_des:.2f} °C")
                print(f"Deadband Range:         {T_des - DEADBAND_C:.2f} °C to {T_des + DEADBAND_C:.2f} °C")
                print("")
                print("--- SENSOR READINGS ---")
                print(f"Enclosure Temp (DAQ 5): {fmt_temp(enclosure_temp)}")
                print(f"Extra DAQ Temp (Ch 6):  {fmt_temp(enclosure_temp_ch6)}")
                print(f"Water Heater Inlet:     {fmt_temp(tank_inlet)}")
                print(f"Water Heater Outlet:    {fmt_temp(tank_outlet)}")
                print(f"HEX Inlet:              {fmt_temp(hex_inlet)}")
                print(f"HEX Outlet:             {fmt_temp(hex_outlet)}")
                print("")
                print("--- FSM INPUTS ---")
                print(f"T_amb used by FSM:      {fmt_temp(T_amb)}")
                print(f"T_tank used by FSM:     {fmt_temp(T_tank)}")
                print("")
                print("--- FSM STATES ---")
                print(f"AHU State:              {ahu_state.name}")
                print(f"TES State:              {tes_state.name}")
                print(f"Case ID:                {case_id}")
                print("")
                print("--- OUTPUT COMMANDS ---")
                print(f"Valve Command:          {valve_cmd}")
                print(f"Blower Command:         {blower_cmd}")
                print(f"Pump Command:           {pump_cmd}")
                print(f"Heater Command:         {heater_cmd}")
                print("")
                print_component_times_for_state(component_times_by_state, state_key)
                print_total_component_times(component_times_by_state)
                print("============================================================\n")

                log_data(
                    minute_index,
                    sample_index,
                    elapsed_test_time_sec,
                    sim_hour,
                    sim_minute,
                    peak_state,
                    T_des,
                    enclosure_temp,
                    enclosure_temp_ch6,
                    tank_inlet,
                    tank_outlet,
                    hex_inlet,
                    hex_outlet,
                    T_tank,
                    ahu_state.name,
                    tes_state.name,
                    case_id,
                    valve_cmd,
                    blower_cmd,
                    pump_cmd,
                    heater_cmd,
                    state_key,
                    state_times["valve"],
                    state_times["blower"],
                    state_times["pump"],
                    state_times["heater"],
                )

                elapsed = time.time() - sample_start_time
                sleep_time = max(0, SAMPLE_INTERVAL_SEC - elapsed)

                # Do not sleep after the final sample.
                if sample_counter < total_samples:
                    time.sleep(sleep_time)

    finally:
        set_outputs(False, False, False, False)
        GPIO.cleanup()
        print("Test finished. Outputs turned OFF and GPIO cleaned up.")
        print(f"Log saved to: {LOG_FILE}")

if __name__ == "__main__":
    run_continuous_test()