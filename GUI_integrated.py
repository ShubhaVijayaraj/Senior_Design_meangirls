import sys
import os
import glob
import csv
import time
import subprocess
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Qt5Agg')  # Forces Matplotlib to use the Qt framework
import matplotlib.pyplot as plt
from matplotlib.figure import Figure # Added this import
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from datetime import datetime
from PyQt5 import QtWidgets, QtCore, QtGui
from enum import IntEnum

# =========================================================
# 1. HARDWARE & GPIO SETUP
# =========================================================
try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    class MockGPIO:
        BCM, OUT, HIGH, LOW = "BCM", "OUT", 1, 0
        def setmode(self, *args): pass
        def setwarnings(self, *args): pass
        def setup(self, *args, **kwargs): pass
        def output(self, *args): pass
        def cleanup(self): pass
    GPIO = MockGPIO()

# Load 1-Wire Drivers
os.system("modprobe w1-gpio")
os.system("modprobe w1-therm")

RELAY_PIN_SOLENOID = 23
RELAY_PIN_FAN = 24
RELAY_PIN_PUMP = 17
RELAY_PIN_HEATER = 27

ACTIVE_HIGH = {"solenoid": False, "fan": True, "pump": True, "heater": True}

class AHUState(IntEnum):
    IDLE = 0; NORMAL = 1; VENT = 2

class TESState(IntEnum):
    IDLE = 0; CHARGING = 1; DISCHARGE = 2

# =========================================================
# 2. CONTINUOUS TEST MATRIX
# =========================================================
CONTINUOUS_TEST = [
    {"sim_hour": 0,  "peak_state": 0, "desired_temp": 21},
    {"sim_hour": 1,  "peak_state": 0, "desired_temp": 21},
    {"sim_hour": 2,  "peak_state": 0, "desired_temp": 21},
    {"sim_hour": 3,  "peak_state": 0, "desired_temp": 21},
    {"sim_hour": 4,  "peak_state": 0, "desired_temp": 21},
    {"sim_hour": 5,  "peak_state": 0, "desired_temp": 24},
    {"sim_hour": 6,  "peak_state": 0, "desired_temp": 24},
    {"sim_hour": 7,  "peak_state": 0, "desired_temp": 24},
    {"sim_hour": 8,  "peak_state": 0, "desired_temp": 24},
    {"sim_hour": 9,  "peak_state": 0, "desired_temp": 24},
    {"sim_hour": 10, "peak_state": 0, "desired_temp": 24},
    {"sim_hour": 11, "peak_state": 0, "desired_temp": 24},
    {"sim_hour": 12, "peak_state": 0, "desired_temp": 24},
    {"sim_hour": 13, "peak_state": 0, "desired_temp": 24},
    {"sim_hour": 14, "peak_state": 1, "desired_temp": 27},
    {"sim_hour": 15, "peak_state": 1, "desired_temp": 27},
    {"sim_hour": 16, "peak_state": 1, "desired_temp": 27},
    {"sim_hour": 17, "peak_state": 1, "desired_temp": 27},
    {"sim_hour": 18, "peak_state": 1, "desired_temp": 27},
    {"sim_hour": 19, "peak_state": 1, "desired_temp": 27},
    {"sim_hour": 20, "peak_state": 0, "desired_temp": 22},
    {"sim_hour": 21, "peak_state": 0, "desired_temp": 22},
    {"sim_hour": 22, "peak_state": 0, "desired_temp": 22},
    {"sim_hour": 23, "peak_state": 0, "desired_temp": 22},
]

# =========================================================
# 3. GUI CLASSES
# =========================================================
class GraphPage(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QtWidgets.QVBoxLayout(self)
        
        # FIXED: Use Figure() and add_subplot() instead of plt.subplots()
        # This prevents the secondary window from opening.
        self.figure = Figure(figsize=(5, 4), dpi=100)
        self.ax = self.figure.add_subplot(111)
        
        self.canvas = FigureCanvas(self.figure)
        self.layout.addWidget(self.canvas)
        self.apply_style()

    def apply_style(self):
        theme_color = '#1B222F'; self.figure.patch.set_facecolor(theme_color); self.ax.set_facecolor(theme_color)
        for spine in self.ax.spines.values(): spine.set_color('#46648C')
        self.ax.tick_params(colors='white', labelsize=10)
        self.ax.xaxis.label.set_color('#7a869a'); self.ax.yaxis.label.set_color('#7a869a')

    def load_excel(self, file_path, is_celsius=True):
        try:
            df = pd.read_excel(file_path); df['Time'] = pd.to_datetime(df['Time'])
            latest_time = df['Time'].max(); start_time = latest_time - pd.Timedelta(hours=24)
            df_filtered = df[df['Time'] > start_time].copy()
            df_filtered['Relative_Hour'] = (df_filtered['Time'] - start_time).dt.total_seconds() / 3600
            self.ax.clear(); self.apply_style()
            y_data = df_filtered['Temperature']; y_label = "Degrees (°C)"; y_min, y_max = 16, 30
            if not is_celsius: y_data = (df_filtered['Temperature'] * 9/5) + 32; y_label = "Degrees (°F)"; y_min, y_max = 60.8, 86
            self.ax.plot(df_filtered['Relative_Hour'], y_data, color='#AAFF7F', linewidth=2, marker='o', markersize=3)
            self.ax.set_title("Temperature Reading Log (Latest 24H)", color='#AAFF7F', fontweight='bold', fontsize=14)
            self.ax.set_xlabel("Time (Hours)"); self.ax.set_ylabel(y_label); self.ax.set_xlim(0, 24); self.ax.set_ylim(y_min, y_max)
            self.ax.grid(True, color='#2D3848', linestyle='--', alpha=0.5); self.canvas.draw()
        except: pass

class DashboardWidget(QtWidgets.QWidget):
    def __init__(self, parent):
        super().__init__(parent); self.p = parent; self.modes_ctrl = ["SMART", "MANUAL"]; self.idx_ctrl = 0; self.init_ui()
    def init_ui(self):
        W, H = 820, 480; label_style = "color: white; font-size: 12px; font-weight: bold; background: transparent;"; btn_w = 160
        self.date_lbl = QtWidgets.QLabel(self); self.date_lbl.setGeometry(20, 15, 250, 25); self.date_lbl.setStyleSheet("color: #7a869a; font-size: 14px; background: transparent;")
        self.time_lbl = QtWidgets.QLabel(self); self.time_lbl.setGeometry(0, 15, W, 25); self.time_lbl.setAlignment(QtCore.Qt.AlignCenter); self.time_lbl.setStyleSheet("color: white; font-size: 14px; background: transparent;")
        self.peak_btn = QtWidgets.QPushButton("PEAK", self); self.peak_btn.setGeometry(W - 130, 15, 110, 25); self.peak_btn.setCursor(QtCore.Qt.PointingHandCursor); self.peak_btn.clicked.connect(self.p.toggle_peak)
        self.main_title = QtWidgets.QLabel("DC HOUSE THERMOSTAT", self); self.main_title.setGeometry(0, 50, W, 40); self.main_title.setAlignment(QtCore.Qt.AlignCenter); self.main_title.setStyleSheet("color: rgb(170, 255, 127); font-size: 24px; font-weight: bold; background: transparent;")
        self.lbl_ctrl = QtWidgets.QLabel("CONTROL MODE", self); self.lbl_ctrl.setGeometry(30, 110, 150, 20); self.lbl_ctrl.setStyleSheet(label_style); self.btn_ctrl = self.make_styled_button("SMART", 30, 140, btn_w, active=True); self.btn_ctrl.clicked.connect(self.toggle_ctrl)
        self.lbl_sys = QtWidgets.QLabel("SYSTEM MODE", self); self.lbl_sys.setGeometry(30, 230, 150, 20); self.lbl_sys.setStyleSheet(label_style); self.btn_sys = self.make_styled_button("HEAT", 30, 260, btn_w, active=False)
        self.lbl_fan = QtWidgets.QLabel("FAN", self); self.lbl_fan.setGeometry(W - 190, 110, 160, 20); self.lbl_fan.setAlignment(QtCore.Qt.AlignRight); self.lbl_fan.setStyleSheet(label_style); self.btn_fan_val = self.make_styled_button("OFF", W - 190, 140, btn_w, active=False)
        self.lbl_state = QtWidgets.QLabel("STATE", self); self.lbl_state.setGeometry(W - 190, 230, 160, 20); self.lbl_state.setAlignment(QtCore.Qt.AlignRight); self.lbl_state.setStyleSheet(label_style); self.btn_state_val = self.make_styled_button("IDLE", W - 190, 260, btn_w, active=False)
        self.temp_val_btn = QtWidgets.QPushButton(self); self.temp_val_btn.setGeometry(int(W/2) - 150, 185, 300, 100); self.temp_val_btn.clicked.connect(self.p.toggle_units); self.temp_val_btn.setCursor(QtCore.Qt.PointingHandCursor); self.temp_val_btn.setStyleSheet("QPushButton { color: white; font-size: 75px; font-weight: bold; background: transparent; border: none; } QPushButton:hover { color: rgba(255, 255, 255, 180); }")
        self.set_text = QtWidgets.QLabel("set", self); self.set_text.setGeometry(0, 275, W, 30); self.set_text.setAlignment(QtCore.Qt.AlignCenter); self.set_text.setStyleSheet("color: #7a869a; font-size: 20px; background: transparent;")
        self.curr_text = QtWidgets.QLabel(self); self.curr_text.setGeometry(0, 425, W, 30); self.curr_text.setAlignment(QtCore.Qt.AlignCenter); self.curr_text.setStyleSheet("color: white; font-size: 18px; background: transparent;")
        pill_style = "QPushButton { background: transparent; color: rgb(110, 150, 200); border: 2px solid rgb(70, 100, 140); border-radius: 20px; font-size: 24px; } QPushButton:hover { border: 2px solid rgb(110, 150, 200); background-color: rgba(110, 150, 200, 25); }"
        self.minus_btn = QtWidgets.QPushButton("—", self); self.minus_btn.setGeometry(int(W/2) - 135, 375, 85, 42); self.minus_btn.clicked.connect(self.p.dec_temp); self.minus_btn.setStyleSheet(pill_style); self.minus_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.plus_btn = QtWidgets.QPushButton("+", self); self.plus_btn.setGeometry(int(W/2) + 45, 375, 85, 42); self.plus_btn.clicked.connect(self.p.inc_temp); self.plus_btn.setStyleSheet(pill_style); self.plus_btn.setCursor(QtCore.Qt.PointingHandCursor)

    def make_styled_button(self, text, x, y, width, active=True):
        btn = QtWidgets.QPushButton(text, self); btn.setGeometry(x, y, width, 55)
        if active:
            btn.setCursor(QtCore.Qt.PointingHandCursor); btn.setStyleSheet("QPushButton { background-color: rgb(45, 56, 72); color: white; border-radius: 12px; font-size: 18px; font-weight: bold; } QPushButton:hover { background-color: rgb(65, 80, 105); border: 1px solid rgb(170, 255, 127); }")
        else: btn.setStyleSheet("QPushButton { background-color: rgb(30, 35, 45); color: rgb(120, 130, 150); border-radius: 12px; font-size: 18px; font-weight: bold; border: 1px solid rgb(50, 60, 75); }")
        return btn
    def toggle_ctrl(self): self.btn_ctrl.setText("MANUAL" if self.btn_ctrl.text() == "SMART" else "SMART"); self.update()
    
    def paintEvent(self, event):
        painter = QtGui.QPainter(self); painter.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = QtCore.QRect(int(820/2) - 130, 120, 260, 260)
        
        # Static Background Arc
        painter.setPen(QtGui.QPen(QtGui.QColor(45, 56, 72), 12, cap=QtCore.Qt.RoundCap))
        painter.drawArc(rect, 225 * 16, -270 * 16)
        
        # Calculate Ratio (Fixed 16-30 Range)
        ratio = (self.p.set_temp_c - 16) / (30 - 16)
        ratio = max(0.0, min(1.0, ratio)) # Guard against overflows
        
        # Create Gradient synced to temperature
        grad = QtGui.QLinearGradient(rect.left(), rect.top(), rect.right(), rect.top())
        grad.setColorAt(0.0, QtGui.QColor(0, 150, 255))   # Blue
        grad.setColorAt(0.6, QtGui.QColor(255, 80, 80))   # Light Red
        grad.setColorAt(1.0, QtGui.QColor(255, 0, 0))     # Strong Red
        
        painter.setPen(QtGui.QPen(QtGui.QBrush(grad), 14, cap=QtCore.Qt.RoundCap))
        painter.drawArc(rect, 225 * 16, int(-270 * 16 * ratio))

    def update_ui_elements(self, peak_state):
        now = datetime.now(); self.time_lbl.setText(now.strftime("%I:%M %p")); self.date_lbl.setText(now.strftime("%B %d, %Y"))
        self.temp_val_btn.setText(self.p.format_temp(self.p.set_temp_c)); self.curr_text.setText(f"Currently {self.p.format_temp(self.p.current_temp_c)}")
        self.peak_btn.setText("PEAK" if peak_state else "OFF-PEAK"); self.peak_btn.setStyleSheet(f"color: {'#FF5050' if peak_state else '#AAFF7F'}; font-size: 14px; font-weight: bold; background: transparent; border: none; text-align: right;")

# =========================================================
# 4. MAIN APPLICATION
# =========================================================
class ThermostatApp(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setFixedSize(900, 480); self.setStyleSheet("background-color: rgb(27, 34, 47);")
        
        self.min_temp_c, self.max_temp_c, self.set_temp_c = 16, 30, 24
        self.current_temp_c, self.is_celsius, self.tank_temp_c, self.peak_state = 20.0, True, 45.0, 0
        self.test_minute_index = 0
        self.log_file = "continuous_test_log.csv"

        self.init_hardware(); self.init_gui(); self.initialize_log()

        self.timer_ui = QtCore.QTimer(); self.timer_ui.timeout.connect(self.run_realtime_loop); self.timer_ui.start(1000)
        self.timer_test = QtCore.QTimer(); self.timer_test.timeout.connect(self.run_simulation_step); self.timer_test.start(60000) 
        
        self.run_simulation_step()
        self.current_excel = "temp_updated.xlsx"; self.page2.load_excel(self.current_excel, self.is_celsius)

    def initialize_log(self):
        if not os.path.exists(self.log_file):
            with open(self.log_file, mode="w", newline="") as f:
                csv.writer(f).writerow(["timestamp","minute_index","sim_hour","peak_state","desired_temp_C","enclosure_temp_C","tank_temp_C","ahu_state","tes_state","case_id","valve_cmd","blower_cmd","pump_cmd","heater_cmd"])

    def init_hardware(self):
        GPIO.setmode(GPIO.BCM); GPIO.setwarnings(False)
        for pin in [RELAY_PIN_SOLENOID, RELAY_PIN_FAN, RELAY_PIN_PUMP, RELAY_PIN_HEATER]: GPIO.setup(pin, GPIO.OUT)

    def init_gui(self):
        self.central_widget = QtWidgets.QWidget(); self.setCentralWidget(self.central_widget)
        self.sidebar = QtWidgets.QFrame(self.central_widget); self.sidebar.setGeometry(0, 0, 80, 480); self.sidebar.setStyleSheet("background-color: rgb(15, 20, 28); border-right: 1px solid rgb(70, 100, 140);")
        sidebar_layout = QtWidgets.QVBoxLayout(self.sidebar)
        for i, icon in enumerate(["🏠", "📈", "⚡"]):
            btn = QtWidgets.QPushButton(icon); btn.setFixedSize(60, 60); btn.setCursor(QtCore.Qt.PointingHandCursor); btn.setStyleSheet("font-size: 24px; color: white; background: transparent; border: none;")
            btn.clicked.connect(self.make_page_changer(i)); sidebar_layout.addWidget(btn)
        sidebar_layout.addStretch()
        self.pages = QtWidgets.QStackedWidget(self.central_widget); self.pages.setGeometry(80, 0, 820, 480)
        self.page1 = DashboardWidget(self); self.page2 = GraphPage(); self.page3 = QtWidgets.QWidget() 
        self.pages.addWidget(self.page1); self.pages.addWidget(self.page2); self.pages.addWidget(self.page3)

    def run_simulation_step(self):
        if self.test_minute_index < len(CONTINUOUS_TEST):
            row = CONTINUOUS_TEST[self.test_minute_index]
            self.peak_state = row["peak_state"]
            self.set_temp_c = row["desired_temp"]
            self.test_minute_index += 1
            print(f"[{datetime.now().strftime('%H:%M:%S')}] SIM STEP: Hour {row['sim_hour']} | Target: {self.set_temp_c}")

    def run_realtime_loop(self):
        ahu_s, tes_s, cid = self.tes_ahu_simple(self.current_temp_c, self.set_temp_c, self.tank_temp_c, self.peak_state)
        v, b, p, h = self.actuation_fsm(ahu_s, tes_s)
        if self.tank_temp_c > 70.0: h = False 
        self.set_outputs(v, b, p, h)
        display_state = tes_s.name if tes_s.name != "DISCHARGE" else "DISCHARGING"
        self.page1.btn_fan_val.setText("ON" if b else "OFF"); self.page1.btn_state_val.setText(display_state); self.page1.update_ui_elements(self.peak_state)
        self.log_data(ahu_s, tes_s, cid, v, b, p, h)

    def log_data(self, ahu_s, tes_s, cid, v, b, p, h):
        with open(self.log_file, mode="a", newline="") as f:
            csv.writer(f).writerow([time.strftime("%Y-%m-%d %H:%M:%S"), self.test_minute_index, self.test_minute_index-1, self.peak_state, self.set_temp_c, self.current_temp_c, self.tank_temp_c, ahu_s.name, tes_s.name, cid, v, b, p, h])

    def tes_ahu_simple(self, T_amb, T_des, T_tank, peak_state):
        T_full, T_low = 60.0, 40.0; need_heat = T_amb < (T_des - 0.1); tank_low, tank_full = T_tank <= T_low, T_tank >= T_full
        ahu_s, tes_s, cid = AHUState.IDLE, TESState.IDLE, 0
        if need_heat:
            if peak_state == 1:
                if not tank_low: ahu_s, tes_s, cid = AHUState.VENT, TESState.DISCHARGE, 1
                else: ahu_s, tes_s, cid = AHUState.NORMAL, TESState.IDLE, 2
            else:
                if not tank_full: ahu_s, tes_s, cid = AHUState.NORMAL, TESState.CHARGING, 3
                else: ahu_s, tes_s, cid = AHUState.NORMAL, TESState.IDLE, 4
        else:
            if peak_state == 1: ahu_s, tes_s, cid = AHUState.IDLE, TESState.IDLE, 5
            else:
                if not tank_full: ahu_s, tes_s, cid = AHUState.IDLE, TESState.CHARGING, 6
                else: ahu_s, tes_s, cid = AHUState.IDLE, TESState.IDLE, 7
        return ahu_s, tes_s, cid

    def actuation_fsm(self, ahu, tes):
        v, b, p, h = False, False, False, False
        if tes == TESState.CHARGING: p, h = True, True
        elif tes == TESState.DISCHARGE: v, p = True, True
        if ahu == AHUState.VENT and tes == TESState.DISCHARGE: b = True
        return v, b, p, h

    def set_outputs(self, v, b, p, h):
        def lvl(dev, on): return (GPIO.HIGH if on else GPIO.LOW) if ACTIVE_HIGH[dev] else (GPIO.LOW if on else GPIO.HIGH)
        GPIO.output(RELAY_PIN_SOLENOID, lvl("solenoid", v)); GPIO.output(RELAY_PIN_FAN, lvl("fan", b))
        GPIO.output(RELAY_PIN_PUMP, lvl("pump", p)); GPIO.output(RELAY_PIN_HEATER, lvl("heater", h))

    def make_page_changer(self, i): return lambda: self.pages.setCurrentIndex(i)
    def toggle_units(self): self.is_celsius = not self.is_celsius; self.page1.update(); self.page2.load_excel(self.current_excel, self.is_celsius)
    def toggle_peak(self): self.peak_state = 1 if self.peak_state == 0 else 0
    def inc_temp(self): self.set_temp_c = min(30, self.set_temp_c + 1); self.page1.update()
    def dec_temp(self): self.set_temp_c = max(16, self.set_temp_c - 1); self.page1.update()
    def format_temp(self, c): return f"{int(c)}°C" if self.is_celsius else f"{int((c * 9/5) + 32)}°F"

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv); window = ThermostatApp(); window.show(); sys.exit(app.exec_())
