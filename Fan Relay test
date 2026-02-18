import RPi.GPIO as GPIO
import time

RELAY_PIN = 23

GPIO.setwarnings(False)

GPIO.setmode(GPIO.BCM)

GPIO.setup(RELAY_PIN, GPIO.OUT)

# simple 10 seconds on and 10 seconds off motion to test whether the relay is 
# working
while True:
    GPIO.output(RELAY_PIN, GPIO.HIGH)
    time.sleep(5)
    GPIO.output(RELAY_PIN, GPIO.LOW)
    time.sleep(5)
    
GPIO.cleanup(1)
