from enum import IntEnum
import time
import RPi.GPIO as GPIO
import GUI_code
import auto_temp_FSM


# State Definitions
class AHUState(IntEnum):
    IDLE = 0
    NORMAL = 1
    VENT = 2


class TESState(IntEnum):
    IDLE = 0
    CHARGING = 1
    DISCHARGE = 2


# GPIO Pin Definitions
RELAY_PIN_SOLENOID = 23
RELAY_PIN_FAN = 24
RELAY_PIN_PUMP = 17
#RELAY_PIN_HEATER = 27  



ACTIVE_HIGH = {
    "solenoid": False,
    "fan": True,
    "pump": True,
    "heater": True,
}



def relay_level(device_name: str, command_on: bool) -> int:
    active_high = ACTIVE_HIGH[device_name]
    if active_high:
        return GPIO.HIGH if command_on else GPIO.LOW
    else:
        return GPIO.LOW if command_on else GPIO.HIGH



# GPIO Setup
def setup_gpio():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    GPIO.setup(RELAY_PIN_SOLENOID, GPIO.OUT)
    GPIO.setup(RELAY_PIN_FAN, GPIO.OUT)
    GPIO.setup(RELAY_PIN_PUMP, GPIO.OUT)
    #GPIO.setup(RELAY_PIN_HEATER, GPIO.OUT)

    # Start with everything OFF
    set_outputs(False, False, False, False)


# Output Actuation
def set_outputs(valve_cmd: bool, blower_cmd: bool, pump_cmd: bool, heater_cmd: bool):
    GPIO.output(RELAY_PIN_SOLENOID, relay_level("solenoid", valve_cmd))
    GPIO.output(RELAY_PIN_FAN, relay_level("fan", blower_cmd))
    GPIO.output(RELAY_PIN_PUMP, relay_level("pump", pump_cmd))
   # GPIO.output(RELAY_PIN_HEATER, relay_level("heater", heater_cmd))


# Decision FSM
# Inputs:
#   T_amb      = room temperature
#   T_des      = desired room temperature
#   T_tank     = tank temperature
#   peak_state = 1 for peak, 0 for off-peak
#
# Outputs:
#   AHU state, TES state, case ID

def tes_ahu_simple(T_amb: float, T_des: float, T_tank: float, peak_state: int):
    T_full = 60.0
    T_low = 40.0

    need_heat = T_amb < T_des
    tank_low = T_tank <= T_low
    tank_full = T_tank >= T_full

    ahu_state = AHUState.IDLE
    tes_state = TESState.IDLE
    case_id = 0

    if need_heat:
        if peak_state == 1:  # peak hours
            if not tank_low:
                # peak + need heat + tank above low
                ahu_state = AHUState.VENT
                tes_state = TESState.DISCHARGE
                case_id = 1
            else:
                # peak + need heat + tank low
                ahu_state = AHUState.NORMAL
                tes_state = TESState.IDLE
                case_id = 2
        else:  # off-peak
            if not tank_full:
                # off-peak + need heat + tank not full
                ahu_state = AHUState.NORMAL
                tes_state = TESState.CHARGING
                case_id = 3
            else:
                # off-peak + need heat + tank full
                ahu_state = AHUState.NORMAL
                tes_state = TESState.IDLE
                case_id = 4
    else:
        if peak_state == 1:
            # room OK during peak
            ahu_state = AHUState.IDLE
            tes_state = TESState.IDLE
            case_id = 5
        else:
            if not tank_full:
                # room OK + off-peak + tank not full
                ahu_state = AHUState.IDLE
                tes_state = TESState.CHARGING
                case_id = 6
            else:
                # room OK + off-peak + tank full
                ahu_state = AHUState.IDLE
                tes_state = TESState.IDLE
                case_id = 7

    return ahu_state, tes_state, case_id



# Actuation FSM
# Takes AHU state and TES state and converts them to commands
# Outputs:
#   valve_cmd, blower_cmd, pump_cmd, heater_cmd

def actuation_fsm(ahu_state: AHUState, tes_state: TESState):
    valve_cmd = False
    blower_cmd = False
    pump_cmd = False
    heater_cmd = False

    if tes_state == TESState.IDLE:
        valve_cmd = False
        pump_cmd = False
        heater_cmd = False

    elif tes_state == TESState.CHARGING:
        valve_cmd = False
        pump_cmd = False
        heater_cmd = True

    elif tes_state == TESState.DISCHARGE:
        valve_cmd = True
        pump_cmd = True
        heater_cmd = False


    if ahu_state == AHUState.VENT and tes_state == TESState.DISCHARGE:
        blower_cmd = True
    else:
        blower_cmd = False

    return valve_cmd, blower_cmd, pump_cmd, heater_cmd



# Replace these with real thermocouple / sensor reads later
def read_room_temperature():
    return 22.0


def read_desired_temperature():
    if GUI_code.get_mode() == "Manual":
        return GUI_code.get_desired_temperature()
    else:
        return auto_temp_FSM.read_desired_temperature()


def read_tank_temperature():
    return 55.0


def read_peak_state():
    return 1  



def main():
    setup_gpio()

    try:
        while True:
            # Read inputs
            T_amb = read_room_temperature()
            T_des = read_desired_temperature()
            T_tank = read_tank_temperature()
            peak_state = read_peak_state()

            # Decision FSM
            ahu_state, tes_state, case_id = tes_ahu_simple(
                T_amb, T_des, T_tank, peak_state
            )

            # Actuation FSM
            valve_cmd, blower_cmd, pump_cmd, heater_cmd = actuation_fsm(
                ahu_state, tes_state
            )

            # Send commands to GPIO
            set_outputs(valve_cmd, blower_cmd, pump_cmd, heater_cmd)

            # Debug print
            print("------------------------------------------------")
            print(f"T_amb={T_amb:.1f} C, T_des={T_des:.1f} C, T_tank={T_tank:.1f} C, Peak={peak_state}")
            print(f"AHU State={ahu_state.name}, TES State={tes_state.name}, Case ID={case_id}")
            print(
                f"Valve={valve_cmd}, Blower={blower_cmd}, Pump={pump_cmd}, Heater={heater_cmd}"
            )

            time.sleep(2)

    except KeyboardInterrupt:
        print("Program stopped by user.")

    finally:
        set_outputs(False, False, False, False)
        GPIO.cleanup()
        print("All relays OFF. GPIO cleaned up.")


if __name__ == "__main__":
    main()