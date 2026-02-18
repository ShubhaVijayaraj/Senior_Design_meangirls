from gpiozero import Servo
from gpiozero.pins.pigpio import PiGPIOFactory
from time import sleep

factory = PiGPIOFactory()
servo = Servo(17, min_pulse_width = 0.0005, max_pulse_width = 0.0025,
              pin_factory=factory)


# ----------------------
# Servo Function
# ----------------------
def valve_open():
    pwm.ChangeDutyCycle(5.8)


def valve_close():
    pwm.ChangeDutyCycle(5)
    
    
#servo.min()
#print("Position at", servo.value)
#sleep(5)
#servo.max()
#print("Position at", servo.value)
#sleep(5)
#servo.mid()
#print("Position at", servo.value)
#sleep(5)
#servo.detach()

try:
    while True:
        servo.min()
        sleep(1)
        servo.mid()
        sleep(1)
        servo.max()
        sleep(1)
except KeyboardInterrupt:
        servo.stop()



