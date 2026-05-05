# DC House Smart Thermostat & TES Control System

This repository contains the Python-based control system and GUI for a smart thermostat integrated with a Thermal Energy Storage (TES) tank and an Air Handling Unit (AHU).

## Prerequisites & Installation

To set up your Raspberry Pi to run this program, run the following commands in your terminal:

### 1. Install System Dependencies & Python Packages
```bash
# Update system and install Qt5 + Math libraries
sudo apt update && sudo apt install -y python3-pyqt5 qtbase5-dev qtchooser qt5-qmake qtbase5-dev-tools libatlas-base-dev

# Install Python libraries
pip install pandas matplotlib RPi.GPIO


