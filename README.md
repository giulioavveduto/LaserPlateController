# Laser Plate Controller

Cross-platform Python application for controlling a motorized XY stage and planning automated laser exposure experiments on multiwell plates.

## Implemented

- Leica DMSTC serial communication
- Relative and absolute XY stage movement
- Stage homing
- Simulated stage for hardware-independent development
- Responsive PySide6 interface
- Standard multiwell-plate geometry
- Graphical well selection
- Persistent A1 calibration storage
- Windows and Linux compatibility

## Planned

- Real/simulated stage selector in the interface
- A1 calibration dialog
- Automatic navigation between wells
- Exposure-time and laser-power groups
- Protocol validation and simulation
- Laser remote control
- Incubator monitoring and control
- Experiment logging

## Installation

Create a virtual environment and install:

```bash
python -m pip install PySide6 pyserial