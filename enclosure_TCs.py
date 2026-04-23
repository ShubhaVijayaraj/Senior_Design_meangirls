import subprocess
import time

while True:
  result = subprocess.run(
  ["smtc", "analog", "read", "1"],
  capture_output = True,
  text = True
  )

  temp = result.stdout.strip()
  print("channel 1 temp: ", temp)
  time.sleep(5)
