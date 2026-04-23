import subprocess
import time

while True:
  result = subprocess.run(
  ["smtc", "analog", "read", "5"],
  capture_output = True,
  text = True
  )

  temp = result.stdout.strip()
  print("channel 5 temp: ", temp)
  time.sleep(5)
