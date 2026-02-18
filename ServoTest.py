from gpiozero import Servo
from gpiozero.pins.pigpio import PiGPIOFactory
from time import sleep

factory = PiGPIOFactory()
servo = Servo(17, min_pulse_width = 0.0005, max_pulse_width = 0.0025,
              pin_factory=factory)

discharge_time = 2 # Valve open time, measured in seconds
TES_idle_time = 2 #Valve closed time, measured in seconds



    
    
servo.value = -0.42
sleep(5)
servo.value = 0.37
sleep(5)
#print("Position at", servo.value)
#sleep(5)
#servo.max()
#print("Position at", servo.value)
#sleep(5)
#servo.mid()
#print("Position at", servo.value)
#sleep(5)
#servo.detach()

#try:
    #while True:
        
        

#except KeyboardInterrupt:
        #servo.stop()



