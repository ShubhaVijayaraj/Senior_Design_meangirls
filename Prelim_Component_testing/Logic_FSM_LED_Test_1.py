import time

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


def show_outputs(valve, blower, pump, heater):
    print("Valve :", "ON" if valve else "OFF")
    print("Blower:", "ON" if blower else "OFF")
    print("Pump  :", "ON" if pump else "OFF")
    print("Heater:", "ON" if heater else "OFF")
    print("-------------------------")


while True:
    s = input("Enter state (0,1,2 or q to quit): ")

    if s.lower() == "q":
        break

    state = int(s)
    cmds = ActuationFSM(state)
    show_outputs(*cmds)
