import time
import glob
import os
import RPi.GPIO as GPIO

RELAY_PIN = 27
TEST_DURATION = 600   # 10 minutes (seconds)

HEATER_ON = GPIO.HIGH
HEATER_OFF = GPIO.LOW


# 1-WIRE SETUP

os.system("modprobe w1-gpio")
os.system("modprobe w1-therm")

base_dir = "/sys/bus/w1/devices/"
device_folders = glob.glob(base_dir + "28-*")

if not device_folders:
    print("❌ No 1-wire sensors found")
    exit()

device_files = [folder + "/w1_slave" for folder in device_folders]


# READ TEMP FUNCTION
def read_temp(device_file):
    with open(device_file, "r") as f:
        lines = f.readlines()

    while lines[0].strip()[-3:] != "YES":
        time.sleep(0.2)
        with open(device_file, "r") as f:
            lines = f.readlines()

    temp_pos = lines[1].find("t=")
    if temp_pos != -1:
        temp_string = lines[1][temp_pos + 2:]
        return float(temp_string) / 1000.0

    return None


GPIO.setmode(GPIO.BCM)
GPIO.setup(RELAY_PIN, GPIO.OUT)
GPIO.output(RELAY_PIN, HEATER_OFF)


try:
    print("\n🔥 Heater ON for 10 minutes...")
    GPIO.output(RELAY_PIN, HEATER_ON)

    start_time = time.time()

    while time.time() - start_time < TEST_DURATION:
        elapsed = int(time.time() - start_time)

        print("\n-----------------------------")
        print(f"Time: {elapsed} sec")

        for i, device in enumerate(device_files):
            temp = read_temp(device)
            print(f"Sensor {i+1}: {temp:.2f} °C")

        time.sleep(5)   # update every 5 sec

    print("\n✅ Test complete. Turning heater OFF.")

except KeyboardInterrupt:
    print("\n⚠️ Stopped early.")

finally:
    GPIO.output(RELAY_PIN, HEATER_OFF)
    GPIO.cleanup()
    print("GPIO cleaned up.")