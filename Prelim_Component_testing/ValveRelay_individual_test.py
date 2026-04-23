import RPi.GPIO as GPIO
import time

VALVE_RELAY_PIN = 23

GPIO.setwarnings(False)

GPIO.setmode(GPIO.BCM)

GPIO.setup(VALVE_RELAY_PIN, GPIO.OUT)

# simple 10 seconds on and 10 seconds off motion to test whether the relay is 
# working
while True:
    GPIO.output(VALVE_RELAY_PIN, GPIO.HIGH)
    time.sleep(5)
    GPIO.output(VALVE_RELAY_PIN, GPIO.LOW)
    time.sleep(5)
    
GPIO.cleanup(1)

