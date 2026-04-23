import os
import glob
import csv
import time

try:
    import RPi.GPIO as GPIO
except ImportError:
    print("Running without GPIO hardware. Using mock GPIO.")

    class MockGPIO:
        BCM = OUT = HIGH = LOW = None
        def setmode(self, *args): pass
        def setwarnings(self, *args): pass
        def setup(self, *args): pass
        def output(self, *args): pass
        def cleanup(self): pass

    GPIO = MockGPIO()

# =========================================================
# SETTINGS
# =========================================================
os.system("modprobe w1-gpio")
os.system("modprobe w1-therm")

BASE_DIR = "/sys/bus/w1/devices/"
LOG_FILE = "water_heater_test_log.csv"

RELAY_PIN_HEATER = 27
RELAY_PIN_FAN = 24
HEATER_ON = GPIO.HIGH
HEATER_OFF = GPIO.LOW
FAN_ON = GPIO.HIGH
FAN_OFF = GPIO.LOW

# Replace with your actual 1-wire IDs
SENSOR_MAP = {
    "28-00000034c7d5": "inlet_HEX",
    "28-00000037e0c4": "outlet_HEX",
    "28-00000037009c": "outlet_water_heater",
    "28-0000005b080d": "inlet_waterh_heater",
}

# =========================================================
# GPIO
# =========================================================
def setup_gpio():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(RELAY_PIN_HEATER, GPIO.OUT)
    GPIO.output(RELAY_PIN_HEATER, HEATER_OFF)
    GPIO.setup(RELAY_PIN_FAN, GPIO.OUT)
    GPIO.output(RELAY_PIN_FAN, FAN_OFF)

def heater_on():
    GPIO.output(RELAY_PIN_HEATER, HEATER_ON)
    GPIO.output(RELAY_PIN_FAN, FAN_ON)

def heater_off():
    GPIO.output(RELAY_PIN_HEATER, HEATER_OFF)
    GPIO.output(RELAY_PIN_FAN, FAN_OFF)
# =========================================================
# 1-WIRE READ
# =========================================================
def get_device_folders():
    return glob.glob(BASE_DIR + "28*")

def print_detected_sensor_ids():
    print("Detected 1-wire sensor IDs:")
    for folder in get_device_folders():
        print(" ", folder.split("/")[-1])

def read_watertemp(device_file):
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

def read_all_sensors():
    sensor_data = {}
    for folder in get_device_folders():
        device_id = folder.split("/")[-1]
        temp_c = read_watertemp(folder + "/w1_slave")
        if temp_c is not None and device_id in SENSOR_MAP:
            sensor_data[SENSOR_MAP[device_id]] = temp_c
    return sensor_data

# =========================================================
# LOGGING
# =========================================================
def initialize_log():
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, mode="w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp",
                "inlet_water_heater_temp_C",
                "outlet_water_heater_temp_C",
                "delta_T_heater_C",
                "heater_state"
            ])

def log_data(inlet_temp, outlet_temp, delta_t, heater_state):
    with open(LOG_FILE, mode="a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            time.strftime("%Y-%m-%d %H:%M:%S"),
            inlet_temp,
            outlet_temp,
            delta_t,
            heater_state
        ])

# =========================================================
# MAIN TEST
# =========================================================
def main():
    setup_gpio()
    initialize_log()
    print_detected_sensor_ids()

    required = ["inlet_water_heater", "outlet_water_heater"]

    try:
        heater_on()
        print("Water heater turned ON")
        print("Logging to:", LOG_FILE)

        while True:
            sensors = read_all_sensors()

            missing = [name for name in required if name not in sensors]
            if missing:
                print("WARNING: Missing sensor data")
                print("Missing:", missing)
                print("Sensors found:", sensors)
                time.sleep(1)
                continue

            inlet_temp = sensors["inlet_water_heater"]
            outlet_temp = sensors["outlet_water_heater"]
            delta_t = outlet_temp - inlet_temp

            print("------------------------------------------------")
            print(f"Inlet Water Heater Temp:   {inlet_temp:.2f} C")
            print(f"Outlet Water Heater Temp:  {outlet_temp:.2f} C")
            print(f"Water Heater ΔT:           {delta_t:.2f} C")
            print("Heater State:              ON")

            log_data(inlet_temp, outlet_temp, delta_t, "ON")

            time.sleep(2)

    except KeyboardInterrupt:
        print("Stopping test.")

    finally:
        heater_off()
        GPIO.cleanup()
        print("Water heater OFF. GPIO cleaned up.")

if __name__ == "__main__":
    main()
