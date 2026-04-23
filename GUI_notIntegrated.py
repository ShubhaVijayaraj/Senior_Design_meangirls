import sys
import os
import time
import re
import pandas as pd
import matplotlib
from collections import deque
matplotlib.use('Qt5Agg')
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from datetime import datetime
from PyQt5 import QtWidgets, QtCore, QtGui

# --- HARDWARE BRIDGE (PLACEHOLDERS) ---
def read_one_wire_temp():
    # Placeholder for Tank Temperature
    return 22.0 + (time.time() % 2) 

def read_smtc_temp():
    # Placeholder for Enclosure Temperature
    return 25.0 + (time.time() % 3)

# --- CUSTOM TOUCH SPINNER FOR PAGE 3 ---
class TouchSpinner(QtWidgets.QWidget):
    valueChanged = QtCore.pyqtSignal(int)
    def __init__(self, value=0, min_val=0, max_val=24, parent=None):
        super().__init__(parent)
        self.value = value
        self.min_val = min_val
        self.max_val = max_val
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        btn_style = """
            QPushButton { 
                background-color: #2D3848; color: #AAFF7F; border: 1px solid #46648C; 
                font-size: 16px; font-weight: bold; border-radius: 4px; min-width: 30px; min-height: 30px;
            }
            QPushButton:pressed { background-color: #46648C; }
        """
        self.btn_minus = QtWidgets.QPushButton("-")
        self.btn_minus.setStyleSheet(btn_style)
        self.btn_minus.clicked.connect(self.decrement)
        self.label = QtWidgets.QLabel(str(self.value))
        self.label.setAlignment(QtCore.Qt.AlignCenter)
        self.label.setStyleSheet("color: white; font-size: 14px; font-weight: bold; min-width: 25px;")
        self.btn_plus = QtWidgets.QPushButton("+")
        self.btn_plus.setStyleSheet(btn_style)
        self.btn_plus.clicked.connect(self.increment)
        layout.addWidget(self.btn_minus)
        layout.addWidget(self.label)
        layout.addWidget(self.btn_plus)

    def increment(self):
        if self.value < self.max_val:
            self.value += 1
            self.label.setText(str(self.value))
            self.valueChanged.emit(self.value)
    def decrement(self):
        if self.value > self.min_val:
            self.value -= 1
            self.label.setText(str(self.value))
            self.valueChanged.emit(self.value)

# --- PEAK SCHEDULER PAGE CLASS ---
class PeakSchedulerPage(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(30, 20, 30, 20)
        self.title = QtWidgets.QLabel("WEEKLY PEAK HOUR SETTINGS")
        self.title.setStyleSheet("color: #AAFF7F; font-size: 22px; font-weight: bold; margin-bottom: 15px;")
        self.title.setAlignment(QtCore.Qt.AlignCenter)
        self.layout.addWidget(self.title)
        self.table = QtWidgets.QTableWidget(7, 3)
        self.table.setHorizontalHeaderLabels(["DAY OF WEEK", "PEAK HOURS", "OFF-PEAK HOURS"])
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setStyleSheet("""
            QTableWidget { background-color: #1B222F; color: white; border: 1px solid #46648C; font-size: 14px; border-radius: 10px; }
            QHeaderView::section { background-color: #2D3848; color: #AAFF7F; padding: 10px; font-weight: bold; border-bottom: 2px solid #46648C; text-transform: uppercase; }
        """)
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        self.spinners = []
        for i, day in enumerate(days):
            self.table.setItem(i, 0, QtWidgets.QTableWidgetItem(day))
            spin_container = QtWidgets.QWidget()
            spin_layout = QtWidgets.QHBoxLayout(spin_container)
            spin_layout.setContentsMargins(10, 2, 10, 2)
            s_start = TouchSpinner(value=14, min_val=0, max_val=23)
            s_end = TouchSpinner(value=20, min_val=1, max_val=24)
            sep = QtWidgets.QLabel("to"); sep.setStyleSheet("color: #7a869a; font-weight: bold;")
            spin_layout.addWidget(s_start); spin_layout.addWidget(sep); spin_layout.addWidget(s_end)
            self.table.setCellWidget(i, 1, spin_container)
            off_item = QtWidgets.QTableWidgetItem("0-14, 20-24")
            off_item.setForeground(QtGui.QColor("#7a869a"))
            off_item.setTextAlignment(QtCore.Qt.AlignCenter)
            self.table.setItem(i, 2, off_item)
            s_start.valueChanged.connect(lambda _, r=i: self.update_row(r))
            s_end.valueChanged.connect(lambda _, r=i: self.update_row(r))
            self.spinners.append((s_start, s_end))
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.table.verticalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.layout.addWidget(self.table)

    def update_row(self, row):
        s_start, s_end = self.spinners[row]
        start, end = s_start.value, s_end.value
        off_peak_item = self.table.item(row, 2)
        if start >= end:
            off_peak_item.setText("Overlap Error"); off_peak_item.setForeground(QtGui.QColor("#FF5050"))
            return
        off_peak_item.setForeground(QtGui.QColor("#7a869a"))
        txt = f"0-{start}, {end}-24"
        if start == 0: txt = f"{end}-24"
        if end == 24: txt = f"0-{start}"
        off_peak_item.setText(txt)

# --- LIVE GRAPH PAGE CLASS ---
class GraphPage(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QtWidgets.QVBoxLayout(self)
        self.figure = Figure(figsize=(5, 4), dpi=100)
        self.ax = self.figure.add_subplot(111)
        self.canvas = FigureCanvas(self.figure)
        self.layout.addWidget(self.canvas)
        
        self.x_data = deque(maxlen=50)
        self.y_enc = deque(maxlen=50)
        self.y_tank = deque(maxlen=50)
        self.y_desired = deque(maxlen=50)
        self.start_time = time.time()
        self.apply_style()

    def apply_style(self):
        theme_color = '#1B222F'; self.figure.patch.set_facecolor(theme_color); self.ax.set_facecolor(theme_color)
        for spine in self.ax.spines.values(): spine.set_color('#46648C')
        self.ax.tick_params(colors='white', labelsize=10)
        self.ax.xaxis.label.set_color('#7a869a'); self.ax.yaxis.label.set_color('#7a869a')

    def update_live_data(self, enc_temp, tank_temp, desired_temp):
        elapsed = time.time() - self.start_time
        self.x_data.append(elapsed)
        self.y_enc.append(enc_temp)
        self.y_tank.append(tank_temp)
        self.y_desired.append(desired_temp)
        
        self.ax.clear()
        self.apply_style()
        self.ax.plot(list(self.x_data), list(self.y_enc), color='#AAFF7F', linewidth=2, label="Enclosure")
        self.ax.plot(list(self.x_data), list(self.y_tank), color='#50A0FF', linewidth=2, label="Tank")
        self.ax.plot(list(self.x_data), list(self.y_desired), color='#FF5050', linewidth=2, linestyle='--', label="Desired")
        
        self.ax.set_title("Live Temperature Readings", color='#AAFF7F', fontweight='bold', fontsize=14)
        self.ax.set_xlabel("Time (Seconds)"); self.ax.set_ylabel("Degrees (°C)")
        self.ax.legend(facecolor='#1B222F', labelcolor='white', loc='upper left')
        self.ax.grid(True, color='#2D3848', linestyle='--', alpha=0.5)
        self.canvas.draw()

class DashboardWidget(QtWidgets.QWidget):
    def __init__(self, parent):
        super().__init__(parent); self.p = parent; self.modes_ctrl = ["SMART", "MANUAL"]; self.idx_ctrl = 0; self.init_ui()

    def init_ui(self):
        W, H = 820, 480
        lbl_style = "color: white; font-size: 12px; font-weight: bold; background: transparent;"
        self.date_lbl = QtWidgets.QLabel(self); self.date_lbl.setGeometry(20, 15, 250, 25)
        self.date_lbl.setStyleSheet("color: white; font-size: 14px; background: transparent;")
        self.time_lbl = QtWidgets.QLabel(self); self.time_lbl.setGeometry(0, 15, W, 25); self.time_lbl.setAlignment(QtCore.Qt.AlignCenter); self.time_lbl.setStyleSheet("color: white; font-size: 14px; background: transparent;")
        self.peak_btn = QtWidgets.QPushButton("PEAK", self); self.peak_btn.setGeometry(W - 130, 15, 110, 25); self.peak_btn.clicked.connect(self.p.toggle_peak)
        self.main_title = QtWidgets.QLabel("DC HOUSE THERMOSTAT", self); self.main_title.setGeometry(0, 50, W, 40); self.main_title.setAlignment(QtCore.Qt.AlignCenter); self.main_title.setStyleSheet("color: rgb(170, 255, 127); font-size: 24px; font-weight: bold;")
        self.l_ctrl = QtWidgets.QLabel("CONTROL MODE", self); self.l_ctrl.setGeometry(30, 110, 150, 20); self.l_ctrl.setStyleSheet(lbl_style)
        self.l_sys = QtWidgets.QLabel("SYSTEM MODE", self); self.l_sys.setGeometry(30, 230, 150, 20); self.l_sys.setStyleSheet(lbl_style)
        self.l_fan = QtWidgets.QLabel("FAN", self); self.l_fan.setGeometry(W - 190, 110, 160, 20); self.l_fan.setAlignment(QtCore.Qt.AlignRight); self.l_fan.setStyleSheet(lbl_style)
        self.l_state = QtWidgets.QLabel("STATE", self); self.l_state.setGeometry(W - 190, 230, 160, 20); self.l_state.setAlignment(QtCore.Qt.AlignRight); self.l_state.setStyleSheet(lbl_style)
        self.btn_ctrl = self.make_styled_button("SMART", 30, 140, 160); self.btn_ctrl.clicked.connect(self.toggle_ctrl)
        self.btn_sys = self.make_styled_button("HEAT", 30, 260, 160, active=False)
        self.btn_fan_val = self.make_styled_button("OFF", W - 190, 140, 160, active=False)
        self.btn_state_val = self.make_styled_button("IDLE", W - 190, 260, 160, active=False)
        self.temp_val_btn = QtWidgets.QPushButton(self); self.temp_val_btn.setGeometry(int(W/2) - 150, 185, 300, 100); self.temp_val_btn.clicked.connect(self.p.toggle_units)
        self.temp_val_btn.setStyleSheet("QPushButton { color: white; font-size: 75px; font-weight: bold; background: transparent; border: none; } QPushButton:hover { color: rgba(255, 255, 255, 180); }")
        self.curr_text = QtWidgets.QLabel(self); self.curr_text.setGeometry(0, 425, W, 30); self.curr_text.setAlignment(QtCore.Qt.AlignCenter); self.curr_text.setStyleSheet("color: white; font-size: 18px;")
        self.minus_btn = QtWidgets.QPushButton("—", self); self.minus_btn.setGeometry(int(W/2) - 135, 375, 85, 42); self.minus_btn.clicked.connect(self.p.dec_temp)
        self.plus_btn = QtWidgets.QPushButton("+", self); self.plus_btn.setGeometry(int(W/2) + 45, 375, 85, 42); self.plus_btn.clicked.connect(self.p.inc_temp)

    def make_styled_button(self, text, x, y, width, active=True):
        btn = QtWidgets.QPushButton(text, self); btn.setGeometry(x, y, width, 55)
        if active: btn.setStyleSheet("QPushButton { background-color: rgb(45, 56, 72); color: white; border-radius: 12px; font-size: 18px; font-weight: bold; } QPushButton:hover { background-color: rgb(65, 80, 105); border: 1px solid rgb(170, 255, 127); }")
        else: btn.setStyleSheet("QPushButton { background-color: rgb(30, 35, 45); color: rgb(120, 130, 150); border-radius: 12px; font-size: 18px; font-weight: bold; border: 1px solid rgb(50, 60, 75); }")
        return btn
    def toggle_ctrl(self): self.idx_ctrl = (self.idx_ctrl + 1) % len(self.modes_ctrl); self.btn_ctrl.setText(self.modes_ctrl[self.idx_ctrl]); self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self); painter.setRenderHint(QtGui.QPainter.Antialiasing)
        sx, sy = self.width() / 820, self.height() / 480
        painter.scale(sx, sy)
        cx, cy = 820 // 2, 480 // 2
        rect = QtCore.QRect(cx - 130, 120, 260, 260)
        painter.setPen(QtGui.QPen(QtGui.QColor(45, 56, 72), 12, cap=QtCore.Qt.RoundCap)); painter.drawArc(rect, 225 * 16, -270 * 16)
        ratio = max(0, min(1, (self.p.set_temp_c - 16) / (45 - 16)))
        grad = QtGui.QLinearGradient(rect.left(), rect.top(), rect.right(), rect.top()); grad.setColorAt(0.0, QtGui.QColor(0, 150, 255)); grad.setColorAt(0.6, QtGui.QColor(255, 80, 80)); grad.setColorAt(1.0, QtGui.QColor(255, 0, 0))
        painter.setPen(QtGui.QPen(QtGui.QBrush(grad), 14, cap=QtCore.Qt.RoundCap)); painter.drawArc(rect, 225 * 16, int(-270 * 16 * ratio))

    def update_ui_elements(self):
        now = datetime.now()
        self.time_lbl.setText(now.strftime("%I:%M %p"))
        self.date_lbl.setText(now.strftime("%B %d, %Y"))
        avg_scale = ((self.width() / 820) + (self.height() / 480)) / 2
        self.temp_val_btn.setText(self.p.format_temp(self.p.set_temp_c))
        
        self.curr_text.setText(f"Currently {self.p.format_temp(self.p.current_temp_c)}")
        
        is_smart = self.btn_ctrl.text() == "SMART"
        peak_color = "#FF5050" if self.p.peak_state else "#AAFF7F"
        
        # PEAK Button logic - Only hover if NOT smart
        if is_smart:
            self.peak_btn.setStyleSheet(f"color: {peak_color}; font-size: {int(14 * avg_scale)}px; font-weight: bold; background: transparent; border: none; text-align: right;")
            self.peak_btn.setCursor(QtCore.Qt.ArrowCursor)
        else:
            self.peak_btn.setStyleSheet(f"QPushButton {{ color: {peak_color}; font-size: {int(14 * avg_scale)}px; font-weight: bold; background: transparent; border: none; text-align: right; }} QPushButton:hover {{ color: white; }}")
            self.peak_btn.setCursor(QtCore.Qt.PointingHandCursor)

        self.peak_btn.setText("PEAK" if self.p.peak_state else "OFF-PEAK")

        pill_style_base = f"background: transparent; color: rgb(110, 150, 200); border: 2px solid rgb(70, 100, 140); border-radius: {int(20*avg_scale)}px; font-size: {int(24*avg_scale)}px;"
        if is_smart:
            final_style = f"QPushButton {{ {pill_style_base} }}"
            self.minus_btn.setCursor(QtCore.Qt.ArrowCursor); self.plus_btn.setCursor(QtCore.Qt.ArrowCursor)
        else:
            final_style = f"QPushButton {{ {pill_style_base} }} QPushButton:hover {{ border: 2px solid rgb(110, 150, 200); background-color: rgba(110, 150, 200, 25); }}"
            self.minus_btn.setCursor(QtCore.Qt.PointingHandCursor); self.plus_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.minus_btn.setStyleSheet(final_style); self.plus_btn.setStyleSheet(final_style)

# --- SCALING STACK HELPER ---
class ScalingStack(QtWidgets.QStackedWidget):
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.count() == 0: return
        sx, sy = self.width() / 820, self.height() / 480
        avg_scale = (sx + sy) / 2
        for i in range(self.count()):
            page = self.widget(i)
            for child in page.findChildren(QtWidgets.QWidget):
                if page.__class__.__name__ == "DashboardWidget":
                    if hasattr(child, '_orig_geo'): geo = child._orig_geo
                    else:
                        geo = child.geometry()
                        child._orig_geo = geo
                    child.setGeometry(int(geo.x()*sx), int(geo.y()*sy), int(geo.width()*sx), int(geo.height()*sy))
                if hasattr(child, '_orig_style'): style = child._orig_style
                else:
                    style = child.styleSheet()
                    child._orig_style = style
                if style and "font-size:" in style:
                    new_style = re.sub(r'font-size:\s*(\d+)px', lambda m: f'font-size: {int(int(m.group(1)) * avg_scale)}px', style)
                    child.setStyleSheet(new_style)
            if isinstance(page, PeakSchedulerPage):
                f = page.table.font(); f.setPointSize(int(12 * avg_scale)); page.table.setFont(f)
                h_f = page.table.horizontalHeader().font(); h_f.setPointSize(int(11 * avg_scale)); page.table.horizontalHeader().setFont(h_f)

class ThermostatApp(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__(); self.setMinimumSize(900, 480); self.setStyleSheet("background-color: rgb(27, 34, 47);")
        self.min_temp_c, self.max_temp_c, self.set_temp_c = 16, 45, 24
        self.current_temp_c, self.tank_temp_c = 20.0, 22.0
        self.is_celsius, self.peak_state = True, True
        self.central_widget = QtWidgets.QWidget(); self.setCentralWidget(self.central_widget)
        self.main_layout = QtWidgets.QHBoxLayout(self.central_widget); self.main_layout.setContentsMargins(0, 0, 0, 0); self.main_layout.setSpacing(0)
        self.sidebar = QtWidgets.QFrame(); self.sidebar.setFixedWidth(80); self.sidebar.setStyleSheet("background-color: rgb(15, 20, 28); border-right: 1px solid rgb(70, 100, 140);")
        sidebar_layout = QtWidgets.QVBoxLayout(self.sidebar)
        for i, icon in enumerate(["🏠", "📈", "⚡"]):
            btn = QtWidgets.QPushButton(icon); btn.setFixedSize(60, 60); btn.setCursor(QtCore.Qt.PointingHandCursor); btn.setStyleSheet("font-size: 24px; color: white; background: transparent; border: none;")
            btn.clicked.connect(self.make_page_changer(i)); sidebar_layout.addWidget(btn)
        sidebar_layout.addStretch()
        self.pages = ScalingStack()
        self.page1, self.page2, self.page3 = DashboardWidget(self), GraphPage(), PeakSchedulerPage(self)
        self.pages.addWidget(self.page1); self.pages.addWidget(self.page2); self.pages.addWidget(self.page3)
        self.main_layout.addWidget(self.sidebar); self.main_layout.addWidget(self.pages)
        self.timer = QtCore.QTimer(); self.timer.timeout.connect(self.global_update); self.timer.start(1000)

    def global_update(self):
        self.current_temp_c = read_smtc_temp()
        self.tank_temp_c = read_one_wire_temp()
        
        if self.page1.btn_ctrl.text() == "SMART":
            now = datetime.now()
            day_idx = now.weekday()
            current_hour = now.hour
            s_start, s_end = self.page3.spinners[day_idx]
            if s_start.value <= current_hour < s_end.value:
                self.peak_state = True
            else:
                self.peak_state = False
                
        self.page1.update_ui_elements()
        self.page2.update_live_data(self.current_temp_c, self.tank_temp_c, self.set_temp_c)

    def make_page_changer(self, index): return lambda: self.pages.setCurrentIndex(index)
    def toggle_units(self): self.is_celsius = not self.is_celsius; self.page1.update()
    
    def toggle_peak(self): 
        if self.page1.btn_ctrl.text() != "SMART":
            self.peak_state = not self.peak_state
            self.page1.update()
            
    def inc_temp(self):
        if self.page1.btn_ctrl.text() != "SMART": self.set_temp_c = min(self.max_temp_c, self.set_temp_c + 1); self.page1.update()
    def dec_temp(self):
        if self.page1.btn_ctrl.text() != "SMART": self.set_temp_c = max(self.min_temp_c, self.set_temp_c - 1); self.page1.update()
    def format_temp(self, temp_c): return f"{int(temp_c)}°C" if self.is_celsius else f"{int((temp_c * 9/5) + 32)}°F"

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv); window = ThermostatApp(); window.show(); sys.exit(app.exec_())
