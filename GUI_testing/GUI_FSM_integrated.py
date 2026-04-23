import sys
import os
import glob
import csv
import time
import subprocess
from enum import IntEnum
from datetime import datetime

import pandas as pd
import matplotlib
matplotlib.use('Qt5Agg')
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from PyQt5 import QtWidgets, QtCore, QtGui

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except Exception:
    GPIO_AVAILABLE = False

    class MockGPIO:
        BCM = "BCM"
        OUT = "OUT"
        HIGH = 1
        LOW = 0

        def setmode(self, mode):
            pass

        def setwarnings(self, flag):
            pass

        def setup(self, pin, mode):
            pass

        def output(self, pin, value):
            pass

        def cleanup(self):
            pass

    GPIO = MockGPIO()

# =========================================================
# 1. LOAD 1-WIRE DRIVERS
# =========================================================
try:
    os.system('modprobe w1-gpio')
    os.system('modprobe w1-therm')
except Exception:
    pass

BASE_DIR = '/sys/bus/w1/devices/'
SENSOR_MAP = {
    '28-00000037009c': 'tank',
}
LOG_FILE = 'tes_ahu_log.csv'
GRAPH_FILE = LOG_FILE

# =========================================================
# 2. STATE DEFINITIONS
# =========================================================
class AHUState(IntEnum):
    IDLE = 0
    NORMAL = 1
    VENT = 2


class TESState(IntEnum):
    IDLE = 0
    CHARGING = 1
    DISCHARGE = 2


# =========================================================
# 3. GPIO PIN DEFINITIONS
# =========================================================
RELAY_PIN_SOLENOID = 23
RELAY_PIN_FAN = 24
RELAY_PIN_PUMP = 17
RELAY_PIN_HEATER = 27

ACTIVE_HIGH = {
    'solenoid': False,
    'fan': True,
    'pump': True,
    'heater': True,
}


def relay_level(device_name: str, command_on: bool) -> int:
    active_high = ACTIVE_HIGH[device_name]
    if active_high:
        return GPIO.HIGH if command_on else GPIO.LOW
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
    GPIO.output(RELAY_PIN_SOLENOID, relay_level('solenoid', valve_cmd))
    GPIO.output(RELAY_PIN_FAN, relay_level('fan', blower_cmd))
    GPIO.output(RELAY_PIN_PUMP, relay_level('pump', pump_cmd))
    GPIO.output(RELAY_PIN_HEATER, relay_level('heater', heater_cmd))


# =========================================================
# 4. 1-WIRE SENSOR READING
# =========================================================
def get_device_folders():
    return glob.glob(BASE_DIR + '28*')


def read_temp(device_file):
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
            return float(lines[1][equals_pos + 2:]) / 1000.0
        return None
    except Exception:
        return None


def read_all_sensors():
    sensor_data = {}
    for folder in get_device_folders():
        device_id = folder.split('/')[-1]
        temp = read_temp(folder + '/w1_slave')
        if temp is not None and device_id in SENSOR_MAP:
            sensor_data[SENSOR_MAP[device_id]] = temp
    return sensor_data


def print_detected_sensor_ids():
    print('Detected 1-wire sensor IDs:')
    for folder in get_device_folders():
        print('  ', folder.split('/')[-1])


# =========================================================
# 4B. DAQ (SMTC)
# =========================================================
def read_temp_smtc(channel):
    try:
        result = subprocess.run(
            ['smtc', 'analog', 'read', str(channel)],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return float(result.stdout.strip())
    except Exception:
        return None


# =========================================================
# 5. DECISION FSM
# =========================================================
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


# =========================================================
# 6. ACTUATION FSM
# =========================================================
def actuation_fsm(ahu_state: AHUState, tes_state: TESState):
    valve_cmd = False
    blower_cmd = False
    pump_cmd = False
    heater_cmd = False

    if tes_state == TESState.CHARGING:
        pump_cmd = True
        heater_cmd = True
    elif tes_state == TESState.DISCHARGE:
        valve_cmd = True
        pump_cmd = True

    if ahu_state == AHUState.VENT and tes_state == TESState.DISCHARGE:
        blower_cmd = True

    return valve_cmd, blower_cmd, pump_cmd, heater_cmd


# =========================================================
# 8. LOGGING
# =========================================================
def initialize_log():
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, mode='w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'timestamp',
                'T_amb_C',
                'T_des_C',
                'T_tank_C',
                'peak_state',
                'ahu_state',
                'tes_state',
                'case_id',
                'valve_cmd',
                'blower_cmd',
                'pump_cmd',
                'heater_cmd',
            ])


def log_data(*row):
    with open(LOG_FILE, mode='a', newline='') as f:
        csv.writer(f).writerow([
            time.strftime('%Y-%m-%d %H:%M:%S'),
            *row,
        ])


# --- GRAPH PAGE CLASS ---
class GraphPage(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QtWidgets.QVBoxLayout(self)
        self.figure = Figure(figsize=(5, 4), dpi=100)
        self.ax = self.figure.add_subplot(111)
        self.canvas = FigureCanvas(self.figure)
        self.layout.addWidget(self.canvas)
        self.apply_style()
        self.draw_placeholder()

    def apply_style(self):
        theme_color = '#1B222F'
        self.figure.patch.set_facecolor(theme_color)
        self.ax.set_facecolor(theme_color)
        for spine in self.ax.spines.values():
            spine.set_color('#46648C')
        self.ax.tick_params(colors='white', labelsize=10)
        self.ax.xaxis.label.set_color('#7a869a')
        self.ax.yaxis.label.set_color('#7a869a')
        self.ax.title.set_color('#AAFF7F')
        legend = self.ax.get_legend()
        if legend is not None:
            legend.remove()

    def c_to_display(self, series, is_celsius=True):
        return series if is_celsius else (series * 9 / 5) + 32

    def draw_placeholder(self):
        self.ax.clear()
        self.apply_style()
        self.ax.set_title('Live Temperature Trends')
        self.ax.text(
            0.5, 0.5,
            'Waiting for live readings...',
            color='white', ha='center', va='center', transform=self.ax.transAxes
        )
        self.canvas.draw()

    def load_log(self, file_path, is_celsius=True):
        try:
            if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
                self.draw_placeholder()
                return

            df = pd.read_csv(file_path)
            if df.empty:
                self.draw_placeholder()
                return

            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.dropna(subset=['timestamp', 'T_amb_C', 'T_des_C', 'T_tank_C']).copy()
            if df.empty:
                self.draw_placeholder()
                return

            first_time = df['timestamp'].iloc[0]
            df['Elapsed_Min'] = (df['timestamp'] - first_time).dt.total_seconds() / 60.0

            self.ax.clear()
            self.apply_style()

            amb = self.c_to_display(df['T_amb_C'], is_celsius)
            tank = self.c_to_display(df['T_tank_C'], is_celsius)
            desired = self.c_to_display(df['T_des_C'], is_celsius)
            y_label = 'Temperature (°C)' if is_celsius else 'Temperature (°F)'

            self.ax.plot(df['Elapsed_Min'], amb, linewidth=2, marker='o', markersize=3, label='Enclosure Temp (Ch 5)')
            self.ax.plot(df['Elapsed_Min'], tank, linewidth=2, marker='o', markersize=3, label='Water Tank Temp')
            self.ax.plot(df['Elapsed_Min'], desired, linewidth=2, linestyle='--', marker='o', markersize=3, label='Desired Temp')

            self.ax.set_title('Live Temperature Trends')
            self.ax.set_xlabel('Time Since Start (min)')
            self.ax.set_ylabel(y_label)
            self.ax.grid(True, color='#2D3848', linestyle='--', alpha=0.5)
            self.ax.legend(facecolor='#1B222F', edgecolor='#46648C', labelcolor='white', loc='best')

            if len(df['Elapsed_Min']) == 1:
                x_val = float(df['Elapsed_Min'].iloc[0])
                self.ax.set_xlim(max(0, x_val - 1), x_val + 1)
            else:
                self.ax.set_xlim(float(df['Elapsed_Min'].min()), float(df['Elapsed_Min'].max()))

            y_all = pd.concat([amb, tank, desired])
            y_min = float(y_all.min())
            y_max = float(y_all.max())
            if y_min == y_max:
                pad = 1.0
            else:
                pad = max(1.0, 0.1 * (y_max - y_min))
            self.ax.set_ylim(y_min - pad, y_max + pad)

            self.canvas.draw()
        except Exception as e:
            self.ax.clear()
            self.apply_style()
            self.ax.text(0.5, 0.5, f'Graph Error\n{str(e)}', color='red', ha='center', va='center', transform=self.ax.transAxes)
            self.canvas.draw()

class DashboardWidget(QtWidgets.QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.p = parent
        self.modes_ctrl = ['SMART', 'MANUAL']
        self.idx_ctrl = 0
        self.modes_sys = ['HEAT', 'COOL']
        self.idx_sys = 0
        self.modes_fan = ['OFF', 'ON']
        self.idx_fan = 0
        self.modes_state = ['IDLE', 'CHARGING', 'DISCHARGING']
        self.idx_state = 0
        self.init_ui()

    def init_ui(self):
        W, H = 820, 480
        self.date_lbl = QtWidgets.QLabel(self)
        self.date_lbl.setGeometry(20, 15, 250, 25)
        self.date_lbl.setStyleSheet('color: #7a869a; font-size: 14px; background: transparent;')

        self.time_lbl = QtWidgets.QLabel(self)
        self.time_lbl.setGeometry(0, 15, W, 25)
        self.time_lbl.setAlignment(QtCore.Qt.AlignCenter)
        self.time_lbl.setStyleSheet('color: white; font-size: 14px; background: transparent;')

        self.peak_btn = QtWidgets.QPushButton('PEAK', self)
        self.peak_btn.setGeometry(W - 130, 15, 110, 25)
        self.peak_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.peak_btn.clicked.connect(self.p.toggle_peak)
        self.peak_btn.setStyleSheet('background: transparent; border: none; font-size: 14px; font-weight: bold; text-align: right;')

        self.main_title = QtWidgets.QLabel('DC HOUSE THERMOSTAT', self)
        self.main_title.setGeometry(0, 50, W, 40)
        self.main_title.setAlignment(QtCore.Qt.AlignCenter)
        self.main_title.setStyleSheet('color: rgb(170, 255, 127); font-size: 24px; font-weight: bold; background: transparent;')

        label_style = 'color: white; font-size: 12px; font-weight: bold; background: transparent;'
        btn_w = 160

        self.lbl_ctrl = QtWidgets.QLabel('CONTROL MODE', self)
        self.lbl_ctrl.setGeometry(30, 110, 150, 20)
        self.lbl_ctrl.setStyleSheet(label_style)
        self.btn_ctrl = self.make_styled_button(self.modes_ctrl[0], 30, 140, btn_w, active=True)
        self.btn_ctrl.clicked.connect(self.toggle_ctrl)

        self.lbl_sys = QtWidgets.QLabel('SYSTEM MODE', self)
        self.lbl_sys.setGeometry(30, 230, 150, 20)
        self.lbl_sys.setStyleSheet(label_style)
        self.btn_sys = self.make_styled_button('HEAT', 30, 260, btn_w, active=False)

        self.lbl_fan = QtWidgets.QLabel('FAN', self)
        self.lbl_fan.setGeometry(W - 190, 110, 160, 20)
        self.lbl_fan.setAlignment(QtCore.Qt.AlignRight)
        self.lbl_fan.setStyleSheet(label_style)
        self.btn_fan_val = self.make_styled_button(self.modes_fan[0], W - 190, 140, btn_w, active=False)

        self.lbl_state = QtWidgets.QLabel('STATE', self)
        self.lbl_state.setGeometry(W - 190, 230, 160, 20)
        self.lbl_state.setAlignment(QtCore.Qt.AlignRight)
        self.lbl_state.setStyleSheet(label_style)
        self.btn_state_val = self.make_styled_button(self.modes_state[0], W - 190, 260, btn_w, active=False)

        self.temp_val_btn = QtWidgets.QPushButton(self)
        self.temp_val_btn.setGeometry(int(W / 2) - 150, 185, 300, 100)
        self.temp_val_btn.clicked.connect(self.p.toggle_units)
        self.temp_val_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.temp_val_btn.setStyleSheet('QPushButton { color: white; font-size: 75px; font-weight: bold; background: transparent; border: none; }')

        self.set_text = QtWidgets.QLabel('set', self)
        self.set_text.setGeometry(0, 275, W, 30)
        self.set_text.setAlignment(QtCore.Qt.AlignCenter)
        self.set_text.setStyleSheet('color: #7a869a; font-size: 20px; background: transparent;')

        self.curr_text = QtWidgets.QLabel(self)
        self.curr_text.setGeometry(0, 425, W, 30)
        self.curr_text.setAlignment(QtCore.Qt.AlignCenter)
        self.curr_text.setStyleSheet('color: white; font-size: 18px; background: transparent;')

        pill_style = 'QPushButton { background: transparent; color: rgb(110, 150, 200); border: 2px solid rgb(70, 100, 140); border-radius: 20px; font-size: 24px; } QPushButton:hover { border: 2px solid rgb(110, 150, 200); background-color: rgba(110, 150, 200, 25); }'
        self.minus_btn = QtWidgets.QPushButton('—', self)
        self.minus_btn.setGeometry(int(W / 2) - 135, 375, 85, 42)
        self.minus_btn.clicked.connect(self.p.dec_temp)
        self.minus_btn.setStyleSheet(pill_style)
        self.minus_btn.setCursor(QtCore.Qt.PointingHandCursor)

        self.plus_btn = QtWidgets.QPushButton('+', self)
        self.plus_btn.setGeometry(int(W / 2) + 45, 375, 85, 42)
        self.plus_btn.clicked.connect(self.p.inc_temp)
        self.plus_btn.setStyleSheet(pill_style)
        self.plus_btn.setCursor(QtCore.Qt.PointingHandCursor)

    def make_styled_button(self, text, x, y, width, active=True):
        btn = QtWidgets.QPushButton(text, self)
        btn.setGeometry(x, y, width, 55)
        if active:
            btn.setCursor(QtCore.Qt.PointingHandCursor)
            btn.setStyleSheet('QPushButton { background-color: rgb(45, 56, 72); color: white; border-radius: 12px; font-size: 18px; font-weight: bold; } QPushButton:hover { background-color: rgb(65, 80, 105); border: 1px solid rgb(170, 255, 127); }')
        else:
            btn.setStyleSheet('QPushButton { background-color: rgb(30, 35, 45); color: rgb(120, 130, 150); border-radius: 12px; font-size: 18px; font-weight: bold; border: 1px solid rgb(50, 60, 75); }')
        return btn

    def toggle_ctrl(self):
        self.idx_ctrl = (self.idx_ctrl + 1) % len(self.modes_ctrl)
        self.btn_ctrl.setText(self.modes_ctrl[self.idx_ctrl])
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = QtCore.QRect(int(820 / 2) - 130, 120, 260, 260)

        painter.setPen(QtGui.QPen(QtGui.QColor(45, 56, 72), 12, cap=QtCore.Qt.RoundCap))
        painter.drawArc(rect, 225 * 16, -270 * 16)

        ratio = (self.p.set_temp_c - 16) / (30 - 16)
        ratio = max(0, min(1, ratio))

        grad = QtGui.QLinearGradient(rect.left(), rect.top(), rect.right(), rect.top())
        grad.setColorAt(0.0, QtGui.QColor(0, 150, 255))
        grad.setColorAt(0.6, QtGui.QColor(255, 80, 80))
        grad.setColorAt(1.0, QtGui.QColor(255, 0, 0))

        painter.setPen(QtGui.QPen(QtGui.QBrush(grad), 14, cap=QtCore.Qt.RoundCap))
        painter.drawArc(rect, 225 * 16, int(-270 * 16 * ratio))

    def update_ui_elements(self):
        now = datetime.now()
        self.time_lbl.setText(now.strftime('%I:%M %p'))
        self.date_lbl.setText(now.strftime('%B %d, %Y'))
        self.temp_val_btn.setText(self.p.format_temp(self.p.set_temp_c))
        self.curr_text.setText(f'Currently {self.p.format_temp(self.p.current_temp_c)}')

        if self.p.peak_state:
            self.peak_btn.setText('PEAK')
            self.peak_btn.setStyleSheet('color: #FF5050; font-size: 14px; font-weight: bold; background: transparent; border: none; text-align: right;')
        else:
            self.peak_btn.setText('OFF-PEAK')
            self.peak_btn.setStyleSheet('color: #AAFF7F; font-size: 14px; font-weight: bold; background: transparent; border: none; text-align: right;')

        self.btn_sys.setText(self.p.system_mode_text)
        self.btn_fan_val.setText('ON' if self.p.blower_cmd else 'OFF')
        self.btn_state_val.setText(self.p.tes_state_text)


class ThermostatApp(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setFixedSize(900, 480)
        self.setStyleSheet('background-color: rgb(27, 34, 47);')

        self.min_temp_c = 16
        self.max_temp_c = 30
        self.set_temp_c = 24
        self.current_temp_c = 20.0
        self.tank_temp_c = 20.0
        self.is_celsius = True
        self.peak_state = True

        self.ahu_state = AHUState.IDLE
        self.tes_state = TESState.IDLE
        self.case_id = 0
        self.valve_cmd = False
        self.blower_cmd = False
        self.pump_cmd = False
        self.heater_cmd = False
        self.system_mode_text = 'HEAT'
        self.tes_state_text = 'IDLE'

        setup_gpio()
        initialize_log()
        print_detected_sensor_ids()

        self.central_widget = QtWidgets.QWidget()
        self.setCentralWidget(self.central_widget)
        self.sidebar = QtWidgets.QFrame(self.central_widget)
        self.sidebar.setGeometry(0, 0, 80, 480)
        self.sidebar.setStyleSheet('background-color: rgb(15, 20, 28); border-right: 1px solid rgb(70, 100, 140);')

        sidebar_layout = QtWidgets.QVBoxLayout(self.sidebar)
        for i, icon in enumerate(['🏠', '📈', '⚡']):
            btn = QtWidgets.QPushButton(icon)
            btn.setFixedSize(60, 60)
            btn.setCursor(QtCore.Qt.PointingHandCursor)
            btn.setStyleSheet('font-size: 24px; color: white; background: transparent; border: none;')
            btn.clicked.connect(self.make_page_changer(i))
            sidebar_layout.addWidget(btn)
        sidebar_layout.addStretch()

        self.pages = QtWidgets.QStackedWidget(self.central_widget)
        self.pages.setGeometry(80, 0, 820, 480)
        self.page1 = DashboardWidget(self)
        self.page2 = GraphPage()
        self.page3 = QtWidgets.QWidget()

        l3 = QtWidgets.QLabel('⚡ System Diagram', self.page3)
        l3.setStyleSheet('color: white; font-size: 20px;')
        l3.setGeometry(0, 0, 820, 480)
        l3.setAlignment(QtCore.Qt.AlignCenter)

        self.pages.addWidget(self.page1)
        self.pages.addWidget(self.page2)
        self.pages.addWidget(self.page3)

        self.page1.update_ui_elements()
        self.page2.load_log(GRAPH_FILE, self.is_celsius)

        self.ui_timer = QtCore.QTimer()
        self.ui_timer.timeout.connect(self.update_time)
        self.ui_timer.start(1000)

        self.fsm_timer = QtCore.QTimer()
        self.fsm_timer.timeout.connect(self.run_fsm_cycle)
        self.fsm_timer.start(2000)

    def make_page_changer(self, index):
        return lambda: self.pages.setCurrentIndex(index)

    def update_time(self):
        self.page1.update_ui_elements()

    def toggle_units(self):
        self.is_celsius = not self.is_celsius
        self.page1.update()
        self.page1.update_ui_elements()
        self.page2.load_log(GRAPH_FILE, self.is_celsius)

    def toggle_peak(self):
        self.peak_state = not self.peak_state
        self.page1.update_ui_elements()
        self.page1.update()

    def inc_temp(self):
        if self.page1.btn_ctrl.text() != 'SMART':
            self.set_temp_c = min(self.max_temp_c, self.set_temp_c + 1)
            self.page1.update_ui_elements()
            self.page1.update()

    def dec_temp(self):
        if self.page1.btn_ctrl.text() != 'SMART':
            self.set_temp_c = max(self.min_temp_c, self.set_temp_c - 1)
            self.page1.update_ui_elements()
            self.page1.update()

    def format_temp(self, temp_c):
        return f'{int(temp_c)}°C' if self.is_celsius else f'{int((temp_c * 9 / 5) + 32)}°F'

    def run_fsm_cycle(self):
        T_amb = read_temp_smtc(5)
        sensors = read_all_sensors()
        T_tank = sensors.get('tank', None)

        if T_amb is None or T_tank is None:
            print('WARNING: Missing temperature data')
            print('1-wire:', sensors)
            return

        T_des = self.set_temp_c
        peak_state = 1 if self.peak_state else 0

        ahu_state, tes_state, case_id = tes_ahu_simple(T_amb, T_des, T_tank, peak_state)
        valve_cmd, blower_cmd, pump_cmd, heater_cmd = actuation_fsm(ahu_state, tes_state)

        if T_tank > 70.0:
            heater_cmd = False

        set_outputs(valve_cmd, blower_cmd, pump_cmd, heater_cmd)

        self.current_temp_c = T_amb
        self.tank_temp_c = T_tank
        self.ahu_state = ahu_state
        self.tes_state = tes_state
        self.case_id = case_id
        self.valve_cmd = valve_cmd
        self.blower_cmd = blower_cmd
        self.pump_cmd = pump_cmd
        self.heater_cmd = heater_cmd
        self.system_mode_text = 'HEAT'
        self.tes_state_text = 'DISCHARGING' if tes_state == TESState.DISCHARGE else tes_state.name

        print('\n================================================')
        print('SYSTEM STATUS')
        peak_str = 'PEAK' if peak_state == 1 else 'OFF-PEAK'
        print(f'Mode: {peak_str}')
        print(f'T_amb (DAQ):        {T_amb:.2f} °C')
        print(f'T_tank (1-wire):    {T_tank:.2f} °C')
        print(f'T_des (setpoint):   {T_des:.2f} °C')
        print('\n--- FSM STATES ---')
        print(f'AHU State: {ahu_state.name}')
        print(f'TES State: {tes_state.name}')
        print(f'Case ID:   {case_id}')
        print('\n--- COMPONENT STATUS ---')
        print(f"Fan:        {'ON' if blower_cmd else 'OFF'}")
        print(f"Pump:       {'ON' if pump_cmd else 'OFF'}")
        print(f"Heater:     {'ON' if heater_cmd else 'OFF'}")
        if valve_cmd:
            valve_mode = 'DISCHARGE (to AHU)'
        else:
            valve_mode = 'CHARGING LOOP' if tes_state == TESState.CHARGING else 'CLOSED / IDLE'
        print(f'Valve(s):   {valve_mode}')
        print('\n--- SYSTEM INSIGHT ---')
        print(f'Tank vs Ambient ΔT: {T_tank - T_amb:.2f} °C')
        if case_id == 1:
            print('Using stored heat (TES discharge during peak)')
        elif case_id == 3:
            print('Charging tank (storing heat)')
        elif case_id == 6:
            print('Charging tank while idle (off-peak)')
        elif case_id in [2, 4]:
            print('Direct heating via heater')
        elif case_id in [5, 7]:
            print('System idle')
        print('================================================\n')

        log_data(
            T_amb, T_des, T_tank, peak_state,
            ahu_state.name, tes_state.name, case_id,
            valve_cmd, blower_cmd, pump_cmd, heater_cmd,
        )

        self.page1.update_ui_elements()
        self.page1.update()
        if self.pages.currentIndex() == 1:
            self.page2.load_log(GRAPH_FILE, self.is_celsius)

    def closeEvent(self, event):
        try:
            set_outputs(False, False, False, False)
            GPIO.cleanup()
        except Exception:
            pass
        event.accept()


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    window = ThermostatApp()
    window.show()
    sys.exit(app.exec_())
