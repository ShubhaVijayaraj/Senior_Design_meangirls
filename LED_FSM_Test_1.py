from gpiozero import LED

VALVE_PIN  = 17 
BLOWER_PIN = 22 
PUMP_PIN   = 27 
HEATER_PIN = 23 

valve_led  = LED(VALVE_PIN)
blower_led = LED(BLOWER_PIN)
pump_led   = LED(PUMP_PIN)
heater_led = LED(HEATER_PIN)

IDLE = 0
CHARGING = 1
DISCHARGING = 2

def ActuationFSM(State):
    ValveCmd  = False
    BlowerCmd = False
    PumpCmd   = False
    HeaterCmd = False

    if State == IDLE:
        pass
    elif State == CHARGING:
        HeaterCmd = True
    elif State == DISCHARGING:
        ValveCmd  = True
        BlowerCmd = True
        PumpCmd   = True

    return ValveCmd, BlowerCmd, PumpCmd, HeaterCmd

def write_outputs(valve, blower, pump, heater):
    valve_led.value  = valve
    blower_led.value = blower
    pump_led.value   = pump
    heater_led.value = heater

try:
    while True:
        s = input("Enter state (0=IDLE, 1=CHARGING, 2=DISCHARGING, q=quit): ")

        if s.lower() == "q":
            break

        if s not in ["0", "1", "2"]:
            print("Invalid. Enter 0, 1, or 2.")
            continue

        state = int(s)
        cmds = ActuationFSM(state)
        write_outputs(*cmds)
        print("Set state =", state)

except KeyboardInterrupt:
    pass
finally:
    write_outputs(False, False, False, False)
    print("Outputs off. Exiting.")
