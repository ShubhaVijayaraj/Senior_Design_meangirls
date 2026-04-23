
import sys
import os
import time
import subprocess
from collections import deque

from PyQt5 import QtWidgets, QtCore
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

WINDOW_TITLE = "Live Temperature Plot"
UPDATE_MS = 500
SIM_DAY_SECONDS = 20.0
MAX_REAL_SECONDS_TO_SHOW = 20.0
SMTC_CHANNEL = 5
ONE_WIRE_ID = "28-00000037009c"
BASE_DIR = "/sys/bus/w1/devices/"

DESIRED_TEMP_SCHEDULE = [
    21, 21, 21, 21, 21,
    24, 24, 24, 24, 24, 24, 24, 24, 24,
    27, 27, 27, 27, 27, 27,
    22, 22, 22, 22
]

PEAK_STATE_SCHEDULE = [
    0,0,0,0,0,0,0,0,0,0,0,0,0,0,
    1,1,1,1,1,1,
    0,0,0,0
]

os.system("modprobe w1-gpio")
os.system("modprobe w1-therm")

def get_one_wire_file(device_id: str):
    path = os.path.join(BASE_DIR, device_id, "w1_slave")
    return path if os.path.exists(path) else None

def read_one_wire_temp(device_id: str):
    device_file = get_one_wire_file(device_id)
    if device_file is None:
        return None
    try:
        with open(device_file, "r") as f:
            lines = f.readlines()
        retries = 0
        while lines and not lines[0].strip().endswith("YES"):
            time.sleep(0.2)
            with open(device_file, "r") as f:
                lines = f.readlines()
            retries += 1
            if retries > 5:
                return None
        if len(lines) < 2:
            return None
        temp_pos = lines[1].find("t=")
        if temp_pos == -1:
            return None
        return float(lines[1][temp_pos + 2:]) / 1000.0
    except Exception:
        return None

def read_smtc_temp(channel: int):
    try:
        result = subprocess.run(
            ["smtc", "analog", "read", str(channel)],
            capture_output=True,
            text=True,
            timeout=3
        )
        if result.returncode != 0:
            return None
        return float(result.stdout.strip())
    except Exception:
        return None

def desired_temp_from_sim_hour(sim_hour: int):
    sim_hour = max(0, min(23, int(sim_hour)))
    return float(DESIRED_TEMP_SCHEDULE[sim_hour])

def peak_state_from_sim_hour(sim_hour: int):
    sim_hour = max(0, min(23, int(sim_hour)))
    return int(PEAK_STATE_SCHEDULE[sim_hour])

class LivePlotWidget(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.start_time = time.time()
        self.real_times = deque()
        self.enclosure_temps = deque()
        self.tank_temps = deque()
        self.desired_temps = deque()
        self.init_ui()
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.update_live_data)
        self.timer.start(UPDATE_MS)

    def init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        title = QtWidgets.QLabel("Live Temperature Plot")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: white;")
        title.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(title)

        self.info_label = QtWidgets.QLabel("Starting...")
        self.info_label.setStyleSheet("font-size: 13px; color: white;")
        self.info_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self.info_label)

        self.figure = Figure(figsize=(9, 5), dpi=100)
        self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.add_subplot(111)
        self.figure.patch.set_facecolor("#1B222F")
        self.ax.set_facecolor("#1B222F")
        layout.addWidget(self.canvas)
        self.setStyleSheet("background-color: #1B222F;")

    def update_live_data(self):
        elapsed_real = time.time() - self.start_time
        cycle_elapsed = elapsed_real % SIM_DAY_SECONDS
        sim_hour_float = (cycle_elapsed / SIM_DAY_SECONDS) * 24.0
        sim_hour = int(sim_hour_float)

        enclosure_temp = read_smtc_temp(SMTC_CHANNEL)
        tank_temp = read_one_wire_temp(ONE_WIRE_ID)
        desired_temp = desired_temp_from_sim_hour(sim_hour)
        peak_state = peak_state_from_sim_hour(sim_hour)

        self.real_times.append(cycle_elapsed)
        self.enclosure_temps.append(enclosure_temp)
        self.tank_temps.append(tank_temp)
        self.desired_temps.append(desired_temp)

        if len(self.real_times) >= 2 and self.real_times[-1] < self.real_times[-2]:
            self.real_times.clear()
            self.enclosure_temps.clear()
            self.tank_temps.clear()
            self.desired_temps.clear()
            self.real_times.append(cycle_elapsed)
            self.enclosure_temps.append(enclosure_temp)
            self.tank_temps.append(tank_temp)
            self.desired_temps.append(desired_temp)

        self.redraw_plot(enclosure_temp, tank_temp, desired_temp, sim_hour, peak_state)

    def redraw_plot(self, enclosure_temp, tank_temp, desired_temp, sim_hour, peak_state):
        self.ax.clear()
        self.ax.set_facecolor("#1B222F")
        for spine in self.ax.spines.values():
            spine.set_color("#46648C")
        self.ax.tick_params(colors="white")
        self.ax.xaxis.label.set_color("white")
        self.ax.yaxis.label.set_color("white")
        self.ax.title.set_color("white")

        x_vals = list(self.real_times)

        def valid_xy(x, y):
            xv, yv = [], []
            for xi, yi in zip(x, y):
                if yi is not None:
                    xv.append(xi)
                    yv.append(yi)
            return xv, yv

        x_enc, y_enc = valid_xy(x_vals, self.enclosure_temps)
        x_tank, y_tank = valid_xy(x_vals, self.tank_temps)
        x_des, y_des = valid_xy(x_vals, self.desired_temps)

        if x_enc:
            self.ax.plot(x_enc, y_enc, linewidth=2, label="Enclosure Temp (Ch 5)")
        if x_tank:
            self.ax.plot(x_tank, y_tank, linewidth=2, label="Water Tank Temp")
        if x_des:
            self.ax.plot(x_des, y_des, linewidth=2, linestyle="--", label="Desired Temp")

        self.ax.set_title("1 Simulated Day = 20 Real Seconds")
        self.ax.set_xlabel("Real Time in Current Run (s)")
        self.ax.set_ylabel("Temperature (°C)")
        self.ax.set_xlim(0, MAX_REAL_SECONDS_TO_SHOW)
        self.ax.grid(True, linestyle="--", alpha=0.4)
        self.ax.legend()
        self.canvas.draw()

        enclosure_str = f"{enclosure_temp:.2f} °C" if enclosure_temp is not None else "N/A"
        tank_str = f"{tank_temp:.2f} °C" if tank_temp is not None else "N/A"
        desired_str = f"{desired_temp:.2f} °C"
        peak_str = "PEAK" if peak_state == 1 else "OFF-PEAK"
        self.info_label.setText(
            f"Sim Hour: {sim_hour:02d}:00   |   Peak: {peak_str}   |   "
            f"Enclosure: {enclosure_str}   |   Tank: {tank_str}   |   Desired: {desired_str}"
        )

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.setFixedSize(1000, 700)
        self.setCentralWidget(LivePlotWidget())

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
