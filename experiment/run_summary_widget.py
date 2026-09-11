from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from experiment.run_report import build_run_rows


class RunSummaryWidget(QGroupBox):
    COLUMNS = [
        ("sequence", "#"),
        ("well", "Well"),
        ("outcome", "Outcome"),
        ("planned_duration_s", "Planned (s)"),
        ("executed_duration_s", "Executed (s)"),
        ("completion_percent", "Completion (%)"),
        ("programmed_current_percent", "Current (%)"),
        ("execution_mode", "Mode"),
    ]

    OUTCOME_LABELS = {
        "completed": "Completed",
        "partial": "Partial",
        "not_started": "Not started",
        "duration_elapsed_not_completed": "Not confirmed",
    }

    MODE_LABELS = {
        "irradiation": "Irradiation",
        "sham_0_percent": "Sham — 0%",
        "stage_only": "Stage only",
    }

    ROW_COLOURS = {
        "completed": "#d7f5df",
        "partial": "#ffe3b3",
        "not_started": "#eeeeee",
        "duration_elapsed_not_completed": "#ffd6d6",
    }

    TERMINAL_STATES = {
        "COMPLETED",
        "STOPPED",
        "ERROR",
    }

    def __init__(self, parent=None) -> None:
        super().__init__("Experiment recap", parent)

        layout = QVBoxLayout(self)

        self.status_label = QLabel(
            "No experiment result is available."
        )
        layout.addWidget(self.status_label)

        self.table = QTableWidget()
        self.table.setColumnCount(len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(
            [label for _, label in self.COLUMNS]
        )
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setMinimumHeight(240)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        header.setSectionResizeMode(
            2,
            QHeaderView.ResizeMode.Stretch,
        )
        header.setSectionResizeMode(
            7,
            QHeaderView.ResizeMode.Stretch,
        )

        layout.addWidget(self.table)

    def clear_summary(self) -> None:
        self.table.setRowCount(0)
        self.status_label.setText(
            "No experiment result is available."
        )
        self.status_label.setStyleSheet("")

    def update_from_runner(self, runner) -> None:
        if not runner.wells:
            self.clear_summary()
            return

        rows = build_run_rows(runner)
        self.table.setRowCount(len(rows))

        for row_index, row in enumerate(rows):
            outcome = str(row["outcome"])
            colour = QColor(
                self.ROW_COLOURS.get(outcome, "#ffffff")
            )

            for column_index, (field, _) in enumerate(
                self.COLUMNS
            ):
                value = row[field]

                if field == "outcome":
                    value = self.OUTCOME_LABELS.get(
                        str(value),
                        str(value),
                    )
                elif field == "execution_mode":
                    value = self.MODE_LABELS.get(
                        str(value),
                        str(value),
                    )
                elif value == "":
                    value = "—"

                item = QTableWidgetItem(str(value))
                item.setBackground(colour)

                if field in {
                    "sequence",
                    "well",
                    "planned_duration_s",
                    "executed_duration_s",
                    "completion_percent",
                    "programmed_current_percent",
                }:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignCenter
                    )

                self.table.setItem(
                    row_index,
                    column_index,
                    item,
                )

        state_name = runner.state.name

        if state_name not in self.TERMINAL_STATES:
            self.status_label.setText(
                "Live summary — executed durations are updated "
                "after pause, completion, stop, or error."
            )
            self.status_label.setStyleSheet("")
            return

        final_off = rows[0]["final_laser_off_confirmed"]

        if final_off == "yes":
            off_text = "Laser OFF confirmed"
            colour = "#16803a"
        elif final_off == "not_applicable":
            off_text = "Laser verification not applicable"
            colour = ""
        else:
            off_text = "Laser OFF not confirmed"
            colour = "#a12626"

        state_text = state_name.replace("_", " ").title()

        self.status_label.setText(
            f"Final state: {state_text} — {off_text}"
        )
        self.status_label.setStyleSheet(
            f"font-weight: bold; color: {colour};"
            if colour
            else "font-weight: bold;"
        )