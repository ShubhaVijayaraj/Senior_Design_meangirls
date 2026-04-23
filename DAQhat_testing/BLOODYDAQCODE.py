import time
import subprocess

SMTC_PATH = "/home/meangirls/Senior_Design_meangirls/smtc-rpi/smtc"

def read_temp(channel):
    try:
        result = subprocess.run(
            [SMTC_PATH, "analog", "read", str(channel)],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode != 0:
            return None

        output = result.stdout.strip()

        try:
            return float(output)
        except ValueError:
            return output

    except Exception:
        return None


while True:
    thermostat_temp = read_temp(1)
    inlet_temp = read_temp(2)

    if thermostat_temp is None:
        print("Failed to read thermostat temperature")
    if inlet_temp is None:
        print("Failed to read fan inlet temperature")

    print(f"Thermostat Temp (Room): {thermostat_temp}")
    print(f"Fan Inlet Temp:         {inlet_temp}")
    print("-----------------------------------")

    time.sleep(5)