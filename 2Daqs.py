import subprocess
import time

def read_temp(channel):
    result = subprocess.run(
        ["smtc", "analog", "read", str(channel)],
        capture_output=True,
        text=True
    )
    return result.stdout.strip()

while True:
    # Read both temperature sensors (now channels 5 and 6)
    thermostat_temp = read_temp(5)   # Room temp (thermostat)
    inlet_temp = read_temp(6)        # Fan inlet temp

    # Print clearly labeled output
    print(f"Thermostat Temp (Room): {thermostat_temp}")
    print(f"Fan Inlet Temp:         {inlet_temp}")
    print("-------------------------------")

    time.sleep(5)