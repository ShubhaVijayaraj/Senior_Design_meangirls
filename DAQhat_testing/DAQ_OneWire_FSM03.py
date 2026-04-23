import os
import glob
import csv
import subprocess
import time
from enum import IntEnum
import RPi.GPIO as GPIO
#GUI Imports 
import tkinter as tk
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from PIL import Image, ImageTk


# ================= ROOT =================
root = tk.Tk()
root.title("DC House Thermostat")
root.geometry("1200x650")
root.configure(bg="#0b0f14")
root.resizable(False, False)
root.update()  # <-- ADD THIS LINE

# ================= COLORS =================
BG = "#0b0f14"
CARD = "#121821"
CARD_DARK = "#0f141c"
ACCENT = "#21d19f"
BLUE = "#3b82f6"
TEXT = "#e5e7eb"
MUTED = "#9ca3af"
INACTIVE = "#1f2937"
WARNING = "#facc15"

# ================= PAGE SYSTEM =================
container = tk.Frame(root, bg=BG)
container.pack(fill="both", expand=True)


page_main = tk.Frame(container, bg=BG)
page_two = tk.Frame(container, bg=BG)

for page in (page_main, page_two):
    page.place(relwidth=1, relheight=1)
   
# ================= BACKGROUND LABELS ======
bg_img = Image.open("cool_to_warm_gradient.png")  # your static gradient image
bg_img = bg_img.resize((1200, 650))
bg_photo = ImageTk.PhotoImage(bg_img)

bg_label_main = tk.Label(page_main, image=bg_photo)
bg_label_second = tk.Label(page_two, image=bg_photo)
bg_label_main.place(x=0, y=0, relwidth=1, relheight=1)
bg_label_second.place(x=0, y=0, relwidth=1, relheight=1)

# Keep a reference to prevent garbage collection
bg_label_main.image = bg_photo
bg_label_second.image = bg_photo


# ================= STATE =================
current_temp = tk.DoubleVar(value=22.0)
target_temp = tk.DoubleVar(value=22.0)
mode = tk.StringVar(value="Auto")
fan_state = tk.StringVar(value="OFF")
unit = tk.StringVar(value="C")
system_state = tk.StringVar(value="Idle")

# ================= CONVERSIONS =================
def c_to_f(c): return c * 9/5 + 32
def f_to_c(f): return (f - 32) * 5/9

# ================= DIAL =================
def draw_dial(temp):
    dial.delete("all")
    center, radius = 150, 110
    start, span = -210, 240

    dial.create_arc(center-radius, center-radius, center+radius, center+radius,
                    start=start, extent=span, style="arc", width=12, outline="#1f2937")

    progress = (temp-15)/15 * span
    dial.create_arc(center-radius, center-radius, center+radius, center+radius,
                    start=start, extent=progress, style="arc", width=12, outline=ACCENT)

    display_temp = temp
    symbol = "°C"
    if unit.get() == "F":
        display_temp = c_to_f(temp)
        symbol = "°F"

    dial.create_text(center, center-5,
                     text=f"{display_temp:.1f}{symbol}",
                     fill=TEXT, font=("Helvetica", 28, "bold"))

    dial.create_text(center, center+22,
                     text="CURRENT TEMPERATURE",
                     fill=MUTED, font=("Helvetica", 9))

    if abs(temp - target_temp.get()) < 0.05:
        dial.create_rectangle(center-45, center+42, center+45, center+62,
                              fill=ACCENT, outline="")
        dial.create_text(center, center+52,
                         text="AT TARGET",
                         fill="black", font=("Helvetica", 9, "bold"))

# ================= FUNCTIONS =================
def update_target_display():
    temp = target_temp.get()
    display_temp = temp
    symbol = "°C"
    if unit.get() == "F":
        display_temp = c_to_f(temp)
        symbol = "°F"
    target_label.config(text=f"{display_temp:.1f}{symbol}")

def update_target(val=None):
    if mode.get() == "Auto":
       return
    target_temp.set(float(val))
    update_target_display()
  #  FSM_code.set_desired_temperature(target_temp.get()) #pushes code to FSM
   

def change_temp(delta):
    if mode.get() == "Auto":
        return  #  do nothing in Auto
   
    new = min(max(target_temp.get() + delta, 15), 30)
    target_temp.set(new)
 #   slider.set(new)
    update_target_display()
  #  FSM_code.set_desired_temperature(new) #pushes code to FSM
   

def set_mode(selected):
    mode.set(selected)
    auto_btn.config(bg=ACCENT if selected == "Auto" else INACTIVE,
                    fg="black" if selected == "Auto" else TEXT)
    manual_btn.config(bg=ACCENT if selected == "Manual" else INACTIVE,
                      fg="black" if selected == "Manual" else TEXT)
 #   FSM_code.set_system_mode(selected) #send mode to FSM
   
 #  if selected == "Auto":
 #       auto_temp = auto_temp_FSM.read_desired_temperature()
 #       target_temp.set(auto_temp)
 #      slider.set(auto_temp)
 #      update_target_display()
 
    # THIS PART CONTROLS SLIDER INTERACTION
 
       
       
def toggle_fan():
    if fan_state.get() == "OFF":
        fan_state.set("ON")
        fan_button.config(bg=ACCENT, fg="black", text="ON")
    else:
        fan_state.set("OFF")
        fan_button.config(bg=INACTIVE, fg=TEXT, text="OFF")

def update_inputs(new_state):
    system_state.set(new_state)
    status_label.config(text=new_state)
    draw_dial(current_temp.get())
    root.after(100, lambda: update_inputs(system_state.get()))

# ================= LEFT CARD =================
left_card = tk.Frame(page_main, bg=CARD, width=380, height=520)
left_card.place(x=100, y=60)

tk.Label(left_card, text="DC House Thermostat",
         fg=MUTED, bg=CARD, font=("Helvetica", 10)).pack(pady=15)

dial = tk.Canvas(left_card, width=300, height=300,
                 bg=CARD, highlightthickness=0)
dial.pack()
draw_dial(current_temp.get())

# ---------- UNIT ----------
unit_frame = tk.Frame(left_card, bg=CARD)
unit_frame.pack()

def set_unit(selected):
    unit.set(selected)
    c_btn.config(bg=ACCENT if selected == "C" else INACTIVE,
                 fg="black" if selected == "C" else TEXT)
    f_btn.config(bg=ACCENT if selected == "F" else INACTIVE,
                 fg="black" if selected == "F" else TEXT)
    update_target_display()

    draw_dial(current_temp.get())

c_btn = tk.Button(unit_frame, text="°C", width=6,
                  bg=ACCENT, fg="black",
                  relief="flat",
                  command=lambda: set_unit("C"))
c_btn.pack(side="left", padx=5)

f_btn = tk.Button(unit_frame, text="°F", width=6,
                  bg=INACTIVE, fg=TEXT,
                  relief="flat",
                  command=lambda: set_unit("F"))
f_btn.pack(side="left", padx=5)

# ================= RIGHT COLUMN =================
right_x = 480

# ---------- TARGET TEMP ----------
target_card = tk.Frame(page_main, bg=CARD, width=600, height=140)
target_card.place(x=right_x, y=60)

tk.Label(target_card, text="TARGET TEMPERATURE",
         fg=MUTED, bg=CARD, font=("Helvetica", 10)).place(x=20, y=15)

target_label = tk.Label(target_card,
                        fg=TEXT, bg=CARD,
                        font=("Helvetica", 28, "bold"))
target_label.place(x=250, y=60)

tk.Button(target_card, text="−", width=4, relief="flat",
          bg=INACTIVE, fg=TEXT,
          command=lambda: change_temp(-0.5)).place(x=160, y=70)

tk.Button(target_card, text="+", width=4, relief="flat",
          bg=INACTIVE, fg=TEXT,
          command=lambda: change_temp(0.5)).place(x=420, y=70)

#slider = ttk.Scale(target_card, from_=15, to=30,
              #     orient="horizontal", length=460,
              #     command=update_target)
#slider.set(22.0)
#slider.place(x=70, y=100)

update_target_display()

# ---------- OPERATING MODE ----------
mode_card = tk.Frame(page_main, bg=CARD, width=600, height=100)
mode_card.place(x=right_x, y=220)

tk.Label(mode_card, text="OPERATING MODE",
         fg=MUTED, bg=CARD, font=("Helvetica", 10)).place(x=20, y=15)

auto_btn = tk.Button(mode_card, text="⚡ Auto", width=18, relief="flat",
                     bg=ACCENT, fg="black",
                     command=lambda: set_mode("Auto"))
auto_btn.place(x=40, y=50)

manual_btn = tk.Button(mode_card, text="⏱ Manual", width=18, relief="flat",
                       bg=INACTIVE, fg=TEXT,
                       command=lambda: set_mode("Manual"))
manual_btn.place(x=260, y=50)

# ---------- SYSTEM MODE CARD ----------
system_mode_card = tk.Frame(page_main, bg=CARD, width=600, height=100)
system_mode_card.place(x=480, y=340)

tk.Label(system_mode_card, text="SYSTEM MODE",
         fg=MUTED, bg=CARD, font=("Helvetica", 10)).place(x=20, y=15)

mode_buttons = []
current_system_mode = tk.StringVar(value="Heating")

for i, (label, name) in enumerate([("❄ Cooling", "Cooling"), ("☀ Heating", "Heating")]):
    def on_click(n=name):
        current_system_mode.set(n)
        for b, bname in mode_buttons:
            if bname == n:
                b.config(bg=ACCENT, fg="black")
            else:
                b.config(bg=INACTIVE, fg=TEXT)

    btn = tk.Button(system_mode_card, text=label, width=20,
                    bg=ACCENT if name == "Heating" else INACTIVE,
                    fg="black" if name == "Heating" else TEXT,
                    relief="flat",
                    command=on_click)
    btn.place(x=40 + i*220, y=50)
    mode_buttons.append((btn, name))

# ---------- FAN CARD ----------
fan_card = tk.Frame(page_main, bg=CARD, width=250, height=90)
fan_card.place(x=510, y=520)

tk.Label(fan_card, text="Fan",
         fg=MUTED, bg=CARD,
         font=("Helvetica", 9)).place(x=20, y=20)

fan_button = tk.Button(fan_card,
                       text="OFF",
                       width=8,
                       relief="flat",
                       bg=INACTIVE,
                       fg=TEXT,
                       command=toggle_fan)
fan_button.place(x=20, y=45)

# ---------- STATUS CARD ----------
status_card = tk.Frame(page_main, bg=CARD, width=250, height=90)
status_card.place(x=810, y=520)

tk.Label(status_card, text="Status",
         fg=MUTED, bg=CARD,
         font=("Helvetica", 9)).place(x=20, y=20)

status_label = tk.Label(status_card,
                        text=system_state.get(),
                        fg=TEXT, bg=CARD,
                        font=("Helvetica", 16, "bold"))
status_label.place(x=20, y=45)

# ================= NAVIGATION BUTTONS =================
tk.Button(page_main, text="Go to Page 2",
          bg=ACCENT, fg="white",
          relief="flat",
          font=("Helvetica", 10, "bold"),
          command=lambda: page_two.tkraise()).place(x=1050, y=20)

# ---------------- PAGE 2 BACK BUTTON ----------------
back_button = tk.Button(page_two, text="Back to Page 1",
                        bg=ACCENT, fg="white",
                        relief="flat",
                        font=("Helvetica", 10, "bold"),
                        command=lambda: page_main.tkraise())
back_button.place(x=1050, y=20)  # coordinates on the page


# ---------------- PAGE 2 GRAPHS ----------------

excel_file = "temperature_thermostat.xlsx"  # Replace with your Excel file
sheet_name_1 = "Temp_data"
sheet_name_2 = "State_data"

data_temp = pd.read_excel(excel_file, sheet_name=sheet_name_1).tail(12)
data_state = pd.read_excel(excel_file, sheet_name=sheet_name_2).tail(12)

# ✅ Convert Time columns to 24-hour format
data_temp['Time'] = pd.to_datetime(data_temp['Time']).dt.strftime('%H:%M')
data_state['Time'] = pd.to_datetime(data_state['Time']).dt.strftime('%H:%M')

# ---------- LINE GRAPH: Temperature over Time ----------
x_temp = data_temp['Time']
y_temp = data_temp['Temperature']

fig1, ax1 = plt.subplots(figsize=(6,3), dpi=100)
ax1.plot(x_temp, y_temp, color=ACCENT, marker='o')
ax1.set_title("Temperature vs Time", color='white')
ax1.set_xlabel("Time", color='white', fontsize=10)
ax1.set_ylabel("Temperature", color='white', fontsize=10)
ax1.tick_params(axis='x', colors='white', rotation = 45)
ax1.tick_params(axis='y', colors='white')
fig1.patch.set_facecolor(BG)
ax1.set_facecolor(CARD)
fig1.subplots_adjust(bottom=0.2)

canvas1 = FigureCanvasTkAgg(fig1, master=page_two)
canvas1.draw()
canvas1.get_tk_widget().place(x=50, y=150, height=350)

# ---------- SCATTER PLOT: Status over Time ----------
x_status = data_state['Time']
y_status = data_state['State']

fig2, ax2 = plt.subplots(figsize=(6,3), dpi=100)
status_mapping = {name: i for i, name in enumerate(data_state['State'].unique())}
y_numeric = data_state['State'].map(status_mapping)

ax2.scatter(x_status, y_numeric, color=BLUE)
ax2.set_title("System Status vs Time", color='white')
ax2.set_xlabel("Time", color='white', fontsize=10)
ax2.set_ylabel("State", color='white', fontsize=10)
ax2.set_yticks(list(status_mapping.values()))
ax2.set_yticklabels(list(status_mapping.keys()), color='white')
ax2.tick_params(axis='x', colors='white', rotation = 45)
fig2.patch.set_facecolor(BG)
ax2.set_facecolor(CARD)
fig2.subplots_adjust(bottom=0.2)

canvas2 = FigureCanvasTkAgg(fig2, master=page_two)
canvas2.draw()
canvas2.get_tk_widget().place(x=600, y=150, height=350)
# ================= START =================
page_main.tkraise()
update_inputs("Idle")
root.mainloop()

# =========================================================
# 1. LOAD 1-WIRE DRIVERS / START OF FSM + ACTUATION LOGIC
# =========================================================
os.system('modprobe w1-gpio')
os.system('modprobe w1-therm')

BASE_DIR = '/sys/bus/w1/devices/'

# Replace these with your real sensor IDs
SENSOR_MAP = {
    "28-aaaaaaaaaaaa": "inlet_hx",
    "28-bbbbbbbbbbbb": "outlet_hx",
    "28-cccccccccccc": "inlet_water_heater",
    "28-dddddddddddd": "outlet_water_heater",
}

LOG_FILE = "tes_ahu_log.csv"


# 2. STATE DEFINITIONS
class AHUState(IntEnum):
    IDLE = 0
    NORMAL = 1
    VENT = 2


class TESState(IntEnum):
    IDLE = 0
    CHARGING = 1
    DISCHARGE = 2


# 3. GPIO PIN DEFINITIONS
RELAY_PIN_SOLENOID = 23
RELAY_PIN_FAN = 24
RELAY_PIN_PUMP = 17
RELAY_PIN_HEATER = 27

ACTIVE_HIGH = {
    "solenoid": False,   # active LOW relay
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


def setup_gpio():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    GPIO.setup(RELAY_PIN_SOLENOID, GPIO.OUT)
    GPIO.setup(RELAY_PIN_FAN, GPIO.OUT)
    GPIO.setup(RELAY_PIN_PUMP, GPIO.OUT)
    GPIO.setup(RELAY_PIN_HEATER, GPIO.OUT)

    set_outputs(False, False, False, False)


def set_outputs(valve_cmd: bool, blower_cmd: bool, pump_cmd: bool, heater_cmd: bool):
    GPIO.output(RELAY_PIN_SOLENOID, relay_level("solenoid", valve_cmd))
    GPIO.output(RELAY_PIN_FAN, relay_level("fan", blower_cmd))
    GPIO.output(RELAY_PIN_PUMP, relay_level("pump", pump_cmd))
    GPIO.output(RELAY_PIN_HEATER, relay_level("heater", heater_cmd))


# 4. SENSOR READING
def get_device_folders():
    return glob.glob(BASE_DIR + '28*')


def read_airtemp(channel):
    try:
        result = subprocess.run(
            ["smtc", "analog", "read", str(channel)],
            capture_output=True,
            text=True
        )

        raw_out = result.stdout.strip()
        raw_err = result.stderr.strip()

        print("[DEBUG] channel", channel, "stdout:", raw_out)
        print("[DEBUG] channel", channel, "stderr:", raw_err)
        print("[DEBUG] channel", channel, "returncode:", result.returncode)

        return float(raw_out)

    except Exception:
        print("[DEBUG] failed reading channel", channel)
        return None

def read_watertemp(device_file):
    try:
        with open(device_file, 'r') as f:
            lines = f.readlines()

        retry = 0
        while lines[0].strip()[-3:] != 'YES':
            time.sleep(0.2)
            with open(device_file, 'r') as f:
                lines = f.readlines()
            retry += 1
            if retry > 5:
                return None

        equals_pos = lines[1].find('t=')
        if equals_pos != -1:
            temp_c = float(lines[1][equals_pos + 2:]) / 1000.0
            return temp_c

        return None

    except Exception:
        return None


def read_all_sensors():
    sensor_data = {}
    device_folders = get_device_folders()

    for folder in device_folders:
        device_id = folder.split('/')[-1]
        watertemp = read_watertemp(folder + '/w1_slave')

        if watertemp is not None and device_id in SENSOR_MAP:
            sensor_data[SENSOR_MAP[device_id]] = watertemp

    return sensor_data


def print_detected_sensor_ids():
    print("Detected 1-wire sensor IDs:")
    for folder in get_device_folders():
        print("  ", folder.split('/')[-1])


# 5. DECISION FSM
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
        if peak_state == 1:
            if not tank_low:
                ahu_state = AHUState.VENT
                tes_state = TESState.DISCHARGE
                case_id = 1
            else:
                ahu_state = AHUState.NORMAL
                tes_state = TESState.IDLE
                case_id = 2
        else:
            if not tank_full:
                ahu_state = AHUState.NORMAL
                tes_state = TESState.CHARGING
                case_id = 3
            else:
                ahu_state = AHUState.NORMAL
                tes_state = TESState.IDLE
                case_id = 4
    else:
        if peak_state == 1:
            ahu_state = AHUState.IDLE
            tes_state = TESState.IDLE
            case_id = 5
        else:
            if not tank_full:
                ahu_state = AHUState.IDLE
                tes_state = TESState.CHARGING
                case_id = 6
            else:
                ahu_state = AHUState.IDLE
                tes_state = TESState.IDLE
                case_id = 7

    return ahu_state, tes_state, case_id


# 6. ACTUATION FSM
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
        pump_cmd = True
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


# 7. OTHER INPUTS
def read_peak_state():
    # replace later with your schedule / utility signal
    return 1


# 8. CSV LOGGING
def initialize_log():
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, mode='w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp",
                "thermostat_temp_C",
                "fan_inlet_temp_C",
                "inlet_hx_temp_C",
                "outlet_hx_temp_C",
                "inlet_water_heater_temp_C",
                "outlet_water_heater_temp_C",
                "T_des_C",
                "T_tank_C",
                "peak_state",
                "ahu_state",
                "tes_state",
                "case_id",
                "valve_cmd",
                "blower_cmd",
                "pump_cmd",
                "heater_cmd"
            ])

def log_data(thermostat_temp, fan_inlet_temp,
             inlet_hx_temp, outlet_hx_temp,
             inlet_water_heater_temp, outlet_water_heater_temp,
             T_des, T_tank, peak_state,
             ahu_state, tes_state, case_id,
             valve_cmd, blower_cmd, pump_cmd, heater_cmd):

    with open(LOG_FILE, mode='a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            time.strftime("%Y-%m-%d %H:%M:%S"),
            thermostat_temp,
            fan_inlet_temp,
            inlet_hx_temp,
            outlet_hx_temp,
            inlet_water_heater_temp,
            outlet_water_heater_temp,
            T_des,
            T_tank,
            peak_state,
            ahu_state.name,
            tes_state.name,
            case_id,
            valve_cmd,
            blower_cmd,
            pump_cmd,
            heater_cmd
        ])

# 9. MAIN LOOP
def main():
    setup_gpio()
    initialize_log()
    print_detected_sensor_ids()

    try:
        while True:
            # ---- Read analog air temperature sensors ----
            thermostat_temp = read_airtemp(5)   # room / thermostat temp
            fan_inlet_temp = read_airtemp(6)    # inlet of fan temp

            # ---- Read 1-wire water tank sensor ----
            sensors = read_all_sensors()
            
            
            required_water_sensors = [
                "inlet_hx",
                "outlet_hx",
                "inlet_water_heater",
                "outlet_water_heater"
            ]

           
            if thermostat_temp is None or fan_inlet_temp is None:
                print("WARNING: Missing analog TC data")
                time.sleep(1)
                continue

            missing = [name for name in required_water_sensors if name not in sensors]
            if missing:
                print("WARNING: Missing 1-wire water sensor data")
                print("Missing:", missing)
                print("Sensors found:", sensors)
                time.sleep(1)
                continue

            # Assign clearly labeled water temperatures
            inlet_hx_temp = sensors["inlet_hx"]
            outlet_hx_temp = sensors["outlet_hx"]
            inlet_water_heater_temp = sensors["inlet_water_heater"]
            outlet_water_heater_temp = sensors["outlet_water_heater"]
            
            # ✅ ADD HERE
            delta_T_HX = outlet_hx_temp - inlet_hx_temp
            delta_T_heater = outlet_water_heater_temp - inlet_water_heater_temp

            # Pick whichever one you want the FSM to use as tank/system water temp
            T_tank = outlet_water_heater_temp

            # Ambient comes from room TC
            T_amb = thermostat_temp

            # Temporary desired temp until GUI exists
            T_des = 25.0
            peak_state = read_peak_state()

            # Decision FSM
            ahu_state, tes_state, case_id = tes_ahu_simple(
                T_amb, T_des, T_tank, peak_state
            )

            # Actuation FSM
            valve_cmd, blower_cmd, pump_cmd, heater_cmd = actuation_fsm(
                ahu_state, tes_state
            )

            # Safety cutoff
            if T_tank > 70.0:
                heater_cmd = False

            # Output to relays
            set_outputs(valve_cmd, blower_cmd, pump_cmd, heater_cmd)

            # Print live data
            print("------------------------------------------------")
            print(f"Thermostat Temp (Room):      {thermostat_temp:.2f} C")
            print(f"Fan Inlet Temp:              {fan_inlet_temp:.2f} C")
            print(f"Inlet HX Temp:               {inlet_hx_temp:.2f} C")
            print(f"Outlet HX Temp:              {outlet_hx_temp:.2f} C")
            print(f"HX ΔT:                       {delta_T_HX:.2f} C")
            print(f"Inlet Water Heater Temp:     {inlet_water_heater_temp:.2f} C")
            print(f"Outlet Water Heater Temp:    {outlet_water_heater_temp:.2f} C")
            print(f"Water Heater ΔT:             {delta_T_heater:.2f} C")
            print(f"Desired Temp:                {T_des:.2f} C")
            print(f"Peak State:                  {peak_state}")
            print(f"AHU State:                   {ahu_state.name}")
            print(f"TES State:                   {tes_state.name}")
            print(f"Case ID:                     {case_id}")
            print(f"Valve={valve_cmd}, Blower={blower_cmd}, Pump={pump_cmd}, Heater={heater_cmd}")

            # ✅ 6. LOG HERE (THIS IS THE RIGHT SPOT)
            log_data(
                thermostat_temp,
                fan_inlet_temp,
                inlet_hx_temp,
                outlet_hx_temp,
                inlet_water_heater_temp,
                outlet_water_heater_temp,
                T_des,
                T_tank,
                peak_state,
                ahu_state,
                tes_state,
                case_id,
                valve_cmd,
                blower_cmd,
                pump_cmd,
                heater_cmd
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
