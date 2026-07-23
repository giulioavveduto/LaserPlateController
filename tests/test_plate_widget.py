import sys

from PySide6.QtWidgets import QApplication, QMainWindow

from plates.plate_geometry import PlateGeometry
from plates.well_plate_widget import WellPlateWidget


def main() -> None:
    app = QApplication(sys.argv)

    plate = PlateGeometry("96-well plate")
    widget = WellPlateWidget(plate)

    window = QMainWindow()
    window.setWindowTitle("96-well plate selector test")
    window.setCentralWidget(widget)
    window.resize(850, 600)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
