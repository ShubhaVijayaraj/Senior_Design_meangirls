import RPi.GPIO as GPIO
import time
from gpiozero import Servo
# ----------------------
# Pin Definitions
# ----------------------
FM_PIN = 17
# GPIO pin 26
def count_pulse(channel):
    global pulse_count
    pulse_count += 1
# ----------------------
                                                                                                                                                                                # GPIO Setup
# ----------------------
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

GPIO.setup(FM_PIN, GPIO.IN, pull_up_down = GPIO.PUD_UP)
GPIO.add_event_detect(FM_PIN, GPIO.RISING, callback = count_pulse)

# ----------------------
# Main Control Logic
try:                                                                                                                                                                                                                                 
    while True:
        pulse_count = 0
        time.sleep(10)
        flow_rate = (pulse_count*6) / 98
        print(" pulse count: ", pulse_count)
        print("flow is: ", flow_rate)
        
    
finally:
    GPIO.cleanup()
    print("GPIO cleaned up")
