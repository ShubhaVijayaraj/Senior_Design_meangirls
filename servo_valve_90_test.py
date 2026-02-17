# -*- coding: utf-8 -*-
"""
Created on Tue Feb 17 16:29:48 2026

@author: Tienna Mensah
"""

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
pwm = GPIO.PWM(SERVO_PIN, 50)
pwm.start(0)  # start with 0% duty cycle

# ----------------------
# Move Servo to 90° (hardcoded)
# ----------------------
try:
    print("Moving valve to 90°...")
    
    GPIO.output(RELAY_PIN, GPIO.HIGH)    # Power the servo
    time.sleep(0.2)                      # Short delay to stabilize
    
    pwm.ChangeDutyCycle(5.83)            # Hardcoded duty cycle for 90°
    time.sleep(2)                         # Wait for servo to reach position
    
    pwm.ChangeDutyCycle(0)               # Stop PWM (optional)
    
    print("Valve now at 90°.")

finally:
    # Keep relay ON if servo needs to hold position, or turn OFF
    # GPIO.output(RELAY_PIN, GPIO.LOW)   # Uncomment to cut power
    pwm.stop()
    GPIO.cleanup()
    print("GPIO cleaned up")
