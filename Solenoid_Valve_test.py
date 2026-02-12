import RPi.GPIO as GPIO
import time

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
pwm.start(0)


# ----------------------
# Servo Function
# ----------------------
def valve_open():
    pwm.ChangeDutyCycle(7.5)
    time.sleep(5)


def valve_close():
    pwm.ChangeDutyCycle(5)
    time.sleep(5)
# ----------------------
# Main Control Logic
# ----------------------
try:
    while True:
        print("Valve Open...")
        
        valve_open()                  # Open valve
        GPIO.output(RELAY_PIN, GPIO.HIGH)  # Turn relay ON
        
        time.sleep(5)

        print("Valve closed supposedy...")
        
        valve_close()                  # Close valve
        GPIO.output(RELAY_PIN, GPIO.LOW)   # Turn relay OFF
        
        time.sleep(5)


finally:
    pwm.stop()
    GPIO.cleanup()
    print("GPIO cleaned up")

