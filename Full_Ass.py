import os
import glob
import time
from enum import IntEnum
import RPi.GPIO as GPIO

# =========================================================
# 1. USER SETTINGS
# =========================================================

# --- Relay pins (BCM numbering) ---
RELAY_PIN_HEATER      = 27   # water heater relay
RELAY_PIN_WH_PUMP     = 17   # pump through water heater loop
RELAY_PIN_HX_PUMP     = 22   # pump through heat exchanger loop
RELAY_PIN_BLOWER      = 24   # blower/fan for enclosure air
RELAY_PIN_VALVE       = 23   # solenoid valve if used

# --- Relay logic ---
# Set True if relay turns ON with GPIO.HIGH
# Set False if relay turns ON with GPIO.LOW
ACTIVE_HIGH = {
    "heater": False,     # example: active LOW relay board
    "wh_pump": False,
    "hx_pump": False,
    "blower": False,
    "valve": False,
}

# --- Temperature control settings (deg C) ---
ENCLOSURE_SETPOINT = 25.0
ENCLOSURE_DEADBAND = 1.0

HOT_WATER_TARGET   = 60.0   # desired hot water temp at heater outlet
HOT_WATER_LOW      = 40.0   # too cold threshold
MAX_WATER_TEMP     = 70.0   # hard safety cutoff
MAX_ENCLOSURE_TEMP = 45.0   # enclosure overtemp safety

# minimum useful temp for heating enclosure
MIN_SUPPLY_TEMP_FOR_HEATING = 45.0

CONTROL_INTERVAL = 2.0  # seconds between control updates


# =========================================================
# 2. 1-WIRE SETUP
# =========================================================
os.system("modprobe w1-gpio")
os.system("modprobe w1-therm")

BASE_DIR = "/sys/bus/w1/devices/"

# Replace these IDs with your actual DS18B20 IDs
SENSOR_MAP = {
    "28-xxxxxxxxxxxx": "wh_inlet",      # water heater inlet
    "28-yyyyyyyyyyyy": "wh_outlet",     # water heater outlet
    "28-zzzzzzzzzzzz": "hx_inlet",      # heat exchanger inlet
    "28-aaaaaaaaaaaa": "hx_outlet",     # heat exchanger outlet
    "28-bbbbbbbbbbbb": "enclosure",     # enclosure air temp
}


# =========================================================
# 3. STATE DEFINITIONS
# =========================================================
class SystemMode(IntEnum):
    IDLE = 0
    CHARGE_WATER = 1
    HEAT_ENCLOSURE = 2
    CHARGE_AND_HEAT = 3
    SAFETY_SHUTDOWN = 4


# =========================================================
# 4. GPIO HELPERS
# =========================================================
def relay_level(device_name: str, command_on: bool) -> int:
    active_high = ACTIVE_HIGH[device_name]
    if active_high:
        return GPIO.HIGH if command_on else GPIO.LOW
    else:
        return GPIO.LOW if command_on else GPIO.HIGH


def setup_gpio():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    GPIO.setup(RELAY_PIN_HEATER, GPIO.OUT)
    GPIO.setup(RELAY_PIN_WH_PUMP, GPIO.OUT)
    GPIO.setup(RELAY_PIN_HX_PUMP, GPIO.OUT)
    GPIO.setup(RELAY_PIN_BLOWER, GPIO.OUT)
    GPIO.setup(RELAY_PIN_VALVE, GPIO.OUT)

    all_outputs_off()


def set_outputs(heater_on, wh_pump_on, hx_pump_on, blower_on, valve_on):
    GPIO.output(RELAY_PIN_HEATER, relay_level("heater", heater_on))
    GPIO.output(RELAY_PIN_WH_PUMP, relay_level("wh_pump", wh_pump_on))
    GPIO.output(RELAY_PIN_HX_PUMP, relay_level("hx_pump", hx_pump_on))
    GPIO.output(RELAY_PIN_BLOWER, relay_level("blower", blower_on))
    GPIO.output(RELAY_PIN_VALVE, relay_level("valve", valve_on))


def all_outputs_off():
    set_outputs(
        heater_on=False,
        wh_pump_on=False,
        hx_pump_on=False,
        blower_on=False,
        valve_on=False
    )


# =========================================================
# 5. 1-WIRE SENSOR READING
# =========================================================
def get_device_folders():
    return glob.glob(BASE_DIR + "28-*")


def print_detected_sensor_ids():
    print("\nDetected 1-wire sensor IDs:")
    folders = get_device_folders()
    if not folders:
        print("  No sensors found")
        return

    for folder in folders:
        print(" ", folder.split("/")[-1])


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

        temp_pos = lines[1].find("t=")
        if temp_pos != -1:
            temp_string = lines[1][temp_pos + 2:]
            return float(temp_string) / 1000.0

        return None

    except Exception:
        return None


def read_all_sensors():
    sensor_data = {}

    for folder in get_device_folders():
        device_id = folder.split("/")[-1]
        device_file = folder + "/w1_slave"
        temp_c = read_temp(device_file)

        if device_id in SENSOR_MAP:
            sensor_data[SENSOR_MAP[device_id]] = temp_c

    return sensor_data


# =========================================================
# 6. CONTROL LOGIC
# =========================================================
def need_enclosure_heat(t_enclosure):
    if t_enclosure is None:
        return False
    return t_enclosure < (ENCLOSURE_SETPOINT - ENCLOSURE_DEADBAND)


def water_is_hot_enough(t_wh_outlet, t_hx_inlet):
    candidates = [t for t in [t_wh_outlet, t_hx_inlet] if t is not None]
    if not candidates:
        return False
    return max(candidates) >= MIN_SUPPLY_TEMP_FOR_HEATING


def water_needs_charging(t_wh_outlet):
    if t_wh_outlet is None:
        return True
    return t_wh_outlet < HOT_WATER_TARGET


def safety_fault(sensors):
    temps = [t for t in sensors.values() if t is not None]

    if not temps:
        return True, "No valid sensor readings"

    if sensors.get("wh_outlet") is not None and sensors["wh_outlet"] >= MAX_WATER_TEMP:
        return True, "Water heater outlet overtemperature"

    if sensors.get("enclosure") is not None and sensors["enclosure"] >= MAX_ENCLOSURE_TEMP:
        return True, "Enclosure overtemperature"

    return False, ""


def decide_mode(sensors):
    t_wh_in   = sensors.get("wh_inlet")
    t_wh_out  = sensors.get("wh_outlet")
    t_hx_in   = sensors.get("hx_inlet")
    t_hx_out  = sensors.get("hx_outlet")
    t_encl    = sensors.get("enclosure")

    fault, reason = safety_fault(sensors)
    if fault:
        return SystemMode.SAFETY_SHUTDOWN, reason

    enclosure_demand = need_enclosure_heat(t_encl)
    water_hot_enough = water_is_hot_enough(t_wh_out, t_hx_in)
    charge_needed = water_needs_charging(t_wh_out)

    # Logic:
    # 1. If enclosure needs heat and water is hot enough -> heat enclosure
    # 2. If enclosure needs heat but water is not hot enough -> charge and heat
    # 3. If enclosure does not need heat but water is below target -> charge water
    # 4. Otherwise idle

    if enclosure_demand and water_hot_enough:
        if charge_needed:
            return SystemMode.CHARGE_AND_HEAT, "Heating enclosure and maintaining water temp"
        else:
            return SystemMode.HEAT_ENCLOSURE, "Heating enclosure"

    if enclosure_demand and not water_hot_enough:
        return SystemMode.CHARGE_AND_HEAT, "Water too cool, charging while heating"

    if (not enclosure_demand) and charge_needed:
        return SystemMode.CHARGE_WATER, "Charging hot water"

    return SystemMode.IDLE, "No heating demand"


def outputs_for_mode(mode):
    heater_on = False
    wh_pump_on = False
    hx_pump_on = False
    blower_on = False
    valve_on = False

    if mode == SystemMode.IDLE:
        pass

    elif mode == SystemMode.CHARGE_WATER:
        heater_on = True
        wh_pump_on = True
        hx_pump_on = False
        blower_on = False
        valve_on = False

    elif mode == SystemMode.HEAT_ENCLOSURE:
        heater_on = False
        wh_pump_on = False
        hx_pump_on = True
        blower_on = True
        valve_on = True

    elif mode == SystemMode.CHARGE_AND_HEAT:
        heater_on = True
        wh_pump_on = True
        hx_pump_on = True
        blower_on = True
        valve_on = True

    elif mode == SystemMode.SAFETY_SHUTDOWN:
        pass

    return heater_on, wh_pump_on, hx_pump_on, blower_on, valve_on


# =========================================================
# 7. DISPLAY
# =========================================================
def fmt_temp(value):
    if value is None:
        return "None"
    return f"{value:.2f} C"


def print_status(sensors, mode, reason, outputs):
    heater_on, wh_pump_on, hx_pump_on, blower_on, valve_on = outputs

    t_wh_in   = sensors.get("wh_inlet")
    t_wh_out  = sensors.get("wh_outlet")
    t_hx_in   = sensors.get("hx_inlet")
    t_hx_out  = sensors.get("hx_outlet")
    t_encl    = sensors.get("enclosure")

    delta_wh = None
    if t_wh_in is not None and t_wh_out is not None:
        delta_wh = t_wh_out - t_wh_in

    delta_hx = None
    if t_hx_in is not None and t_hx_out is not None:
        delta_hx = t_hx_in - t_hx_out

    print("\n================================================")
    print(time.strftime("%Y-%m-%d %H:%M:%S"))
    print(f"Mode: {mode.name}")
    print(f"Reason: {reason}")
    print("------------------------------------------------")
    print(f"WH Inlet     : {fmt_temp(t_wh_in)}")
    print(f"WH Outlet    : {fmt_temp(t_wh_out)}")
    print(f"HX Inlet     : {fmt_temp(t_hx_in)}")
    print(f"HX Outlet    : {fmt_temp(t_hx_out)}")
    print(f"Enclosure    : {fmt_temp(t_encl)}")

    if delta_wh is not None:
        print(f"Water Heater dT : {delta_wh:.2f} C")
    else:
        print("Water Heater dT : None")

    if delta_hx is not None:
        print(f"Heat Exchanger dT : {delta_hx:.2f} C")
    else:
        print("Heat Exchanger dT : None")

    print("------------------------------------------------")
    print(f"Heater   : {heater_on}")
    print(f"WH Pump  : {wh_pump_on}")
    print(f"HX Pump  : {hx_pump_on}")
    print(f"Blower   : {blower_on}")
    print(f"Valve    : {valve_on}")
    print("================================================")


# =========================================================
# 8. MAIN LOOP
# =========================================================
def main():
    setup_gpio()
    print_detected_sensor_ids()

    print("\nStarting full assembly control...")

    try:
        while True:
            sensors = read_all_sensors()

            # make sure all 5 expected sensors are at least present in dict
            for required_name in ["wh_inlet", "wh_outlet", "hx_inlet", "hx_outlet", "enclosure"]:
                if required_name not in sensors:
                    sensors[required_name] = None

            mode, reason = decide_mode(sensors)
            outputs = outputs_for_mode(mode)

            # extra safety override
            if sensors["wh_outlet"] is not None and sensors["wh_outlet"] >= MAX_WATER_TEMP:
                outputs = (False, False, False, False, False)
                mode = SystemMode.SAFETY_SHUTDOWN
                reason = "Extra heater safety cutoff triggered"

            set_outputs(*outputs)
            print_status(sensors, mode, reason, outputs)

            time.sleep(CONTROL_INTERVAL)

    except KeyboardInterrupt:
        print("\nStopped by user.")

    finally:
        all_outputs_off()
        GPIO.cleanup()
        print("All outputs OFF. GPIO cleaned up.")


if __name__ == "__main__":
    main()