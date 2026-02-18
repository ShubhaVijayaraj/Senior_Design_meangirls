import RPi.GPIO as GPIO
import time
from gpiozero import Servo

# ----------------------
# Pin Definitions
# ----------------------
SERVO_PIN = 17      # PWM capable pin
RELAY_PIN = 14      # Digital output for relay

# ----------------------
# GPIO Setup
# ----------------------
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

GPIO.setup(SERVO_PIN, GPIO.OUT)
GPIO.setup(RELAY_PIN, GPIO.OUT)

# Initialize relay OFF
GPIO.output(RELAY_PIN, GPIO.LOW)


# Initialize PWM for servo (50Hz typical)
pwm = GPIO.PWM(SERVO_PIN,50)
pwm.start(5)


# ----------------------
# Servo Function
# ----------------------
def valve_open():
    pwm.ChangeDutyCycle(5.8)


def valve_close():
    pwm.ChangeDutyCycle(5)

# ----------------------
# Main Control Logic
# ----------------------
try:

        
        pwm.ChangeDutyCycle(5.83)
        print("trying")
        time.sleep(10)
        print("now at 90")


finally:
    pwm.stop()
    GPIO.cleanup()
    print("GPIO cleaned up")

