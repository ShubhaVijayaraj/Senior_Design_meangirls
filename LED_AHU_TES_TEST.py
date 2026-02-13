# -*- coding: utf-8 -*-
"""
Created on Fri Feb 13 14:55:23 2026

@author: Owner
"""

from gpiozero import LED

# ------------------------
# GPIO SETUP (BCM pins)
# ------------------------
VALVE_PIN  = 17
BLOWER_PIN = 22
PUMP_PIN   = 27
HEATER_PIN = 23

valve_led  = LED(VALVE_PIN)
blower_led = LED(BLOWER_PIN)
pump_led   = LED(PUMP_PIN)
heater_led = LED(HEATER_PIN)

# ------------------------
# STATE CODES
# ------------------------
AHU_IDLE   = 0
AHU_NORMAL = 1
AHU_VENT   = 2

TES_IDLE       = 0
TES_CHARGING   = 1
TES_DISCHARGE  = 2

# ------------------------
# THRESHOLDS (match your MATLAB)
# ------------------------
T_full = 60.0
T_low  = 40.0


# ------------------------
# Decision FSM (Python version of your MATLAB TES_AHU_Simple)
# ------------------------
def TES_AHU_Simple(T_Amb, T_Des, T_Tank, Peak_State):
    """
    Returns: AHU_State, TES_State, caseID
    """
    needHeat = (T_Amb < T_Des)

    tankLow  = (T_Tank <= T_low)
    tankFull = (T_Tank >= T_full)

    # defaults
    AHU_State = AHU_IDLE
    TES_State = TES_IDLE
    caseID = 0

    if needHeat:
        # NEED HEAT
        if Peak_State == 1:
            # PEAK
            if not tankLow:
                AHU_State = AHU_VENT
                TES_State = TES_DISCHARGE
                caseID = 1
            else:
                AHU_State = AHU_NORMAL
                TES_State = TES_IDLE
                caseID = 2
        else:
            # OFF-PEAK
            # ---- Choose ONE of these rules ----

            # (A) Your earlier verbal rule: charge only if tank is LOW
            if not tankFull:
                AHU_State = AHU_NORMAL
                TES_State = TES_CHARGING
                caseID = 3
            else:
                AHU_State = AHU_NORMAL
                TES_State = TES_IDLE
                caseID = 4

            # (B) If you instead want: charge whenever NOT FULL during off-peak + needHeat
            # if not tankFull:
            #     AHU_State = AHU_NORMAL
            #     TES_State = TES_CHARGING
            #     caseID = 3
            # else:
            #     AHU_State = AHU_NORMAL
            #     TES_State = TES_IDLE
            #     caseID = 4

    else:
        # ROOM OK
        if Peak_State == 1:
            AHU_State = AHU_IDLE
            TES_State = TES_IDLE
            caseID = 5
        else:
            if not tankFull:
                AHU_State = AHU_IDLE
                TES_State = TES_CHARGING
                caseID = 6
            else:
                AHU_State = AHU_IDLE
                TES_State = TES_IDLE
                caseID = 7

    return AHU_State, TES_State, caseID


# ------------------------
# Actuation FSM (your LED mapping)
# State: 0=IDLE, 1=CHARGING, 2=DISCHARGING
# ------------------------
def ActuationFSM(State):
    ValveCmd  = False
    BlowerCmd = False
    PumpCmd   = False
    HeaterCmd = False

    if State == TES_IDLE:
        pass
    elif State == TES_CHARGING:
        HeaterCmd = True
    elif State == TES_DISCHARGE:
        ValveCmd  = True
        BlowerCmd = True
        PumpCmd   = True

    return ValveCmd, BlowerCmd, PumpCmd, HeaterCmd


def write_outputs(valve, blower, pump, heater):
    valve_led.value  = valve
    blower_led.value = blower
    pump_led.value   = pump
    heater_led.value = heater


def all_off():
    write_outputs(False, False, False, False)


# ------------------------
# Interactive test loop
# ------------------------
try:
    while True:
        raw = input("\nEnter: T_Amb T_Des T_Tank Peak(0/1)   or 'q' to quit:\n> ").strip()
        if raw.lower() == "q":
            break

        parts = raw.split()
        if len(parts) != 4:
            print("Format must be exactly 4 numbers, example: 20.5 22 55 1")
            continue

        try:
            T_Amb = float(parts[0])
            T_Des = float(parts[1])
            T_Tank = float(parts[2])
            Peak_State = int(parts[3])
        except ValueError:
            print("Bad input. Example: 20.5 22 55 1")
            continue

        if Peak_State not in (0, 1):
            print("Peak must be 0 or 1.")
            continue

        AHU_State, TES_State, caseID = TES_AHU_Simple(T_Amb, T_Des, T_Tank, Peak_State)

        cmds = ActuationFSM(TES_State)
        write_outputs(*cmds)

        print(f"AHU_State={AHU_State}  TES_State={TES_State}  caseID={caseID}")
        print(f"LEDs -> Valve={cmds[0]} Blower={cmds[1]} Pump={cmds[2]} Heater={cmds[3]}")

except KeyboardInterrupt:
    pass
finally:
    all_off()
    print("Outputs off. Exiting.")

