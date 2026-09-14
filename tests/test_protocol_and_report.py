from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from experiment.experiment_protocol import (
    ExperimentProtocol,
    LaserSetpoint,
)
from experiment.experiment_runner import ExperimentState
from experiment.run_report import (
    FIELDNAMES,
    build_run_rows,
    write_csv_report,
)


class ProtocolTests(unittest.TestCase):
    def test_v1_protocol_remains_compatible(self) -> None:
        protocol = ExperimentProtocol.from_dict(
            {
                "format_version": 1,
                "name": "Legacy protocol",
                "plate_type": "96-well plate",
                "selected_wells": ["A1", "B2"],
                "common_exposure_time_s": 5.0,
            }
        )

        self.assertTrue(protocol.is_valid)
        self.assertFalse(protocol.is_laser_ready)
        self.assertEqual(protocol.estimated_duration_s, 10.0)
        self.assertEqual(protocol.exposure_time_for("A1"), 5.0)
        self.assertEqual(protocol.irradiation_order, "row")

    def test_v2_per_well_assignments_survive_round_trip(self) -> None:
        protocol = ExperimentProtocol(
            name="V2 protocol",
            plate_type="96-well plate",
            selected_wells=["A1", "A2"],
            irradiation_order="serpentine",
            common_exposure_time_s=5.0,
            default_laser_setpoint=LaserSetpoint(
                mode="current_percent",
                value=30.0,
            ),
        )

        protocol.set_exposure_time_for_wells(["A2"], 12.0)
        protocol.set_laser_setpoint_for_wells(
            ["A2"],
            LaserSetpoint(
                mode="current_percent",
                value=55.0,
            ),
        )

        serialized = protocol.to_dict()
        restored = ExperimentProtocol.from_dict(serialized)
        self.assertEqual(
            restored.irradiation_order,
            "serpentine",
        )

        self.assertEqual(serialized["format_version"], 2)
        self.assertTrue(restored.is_valid)
        self.assertTrue(restored.is_laser_ready)
        self.assertEqual(restored.estimated_duration_s, 17.0)
        self.assertEqual(restored.exposure_time_for("A1"), 5.0)
        self.assertEqual(restored.exposure_time_for("A2"), 12.0)
        self.assertEqual(
            restored.laser_setpoint_for("A1").value,
            30.0,
        )
        self.assertEqual(
            restored.laser_setpoint_for("A2").value,
            55.0,
        )

    def test_unknown_irradiation_order_is_rejected(
        self,
    ) -> None:
        data = ExperimentProtocol(
            plate_type="96-well plate",
            selected_wells=["A1"],
            common_exposure_time_s=5.0,
        ).to_dict()

        data["irradiation_order"] = "unknown"

        with self.assertRaises(ValueError):
            ExperimentProtocol.from_dict(data)


class RunReportTests(unittest.TestCase):
    def make_runner(self) -> SimpleNamespace:
        return SimpleNamespace(
            wells=["A1", "A2", "A3"],
            exposure_times_s=[5.0, 10.0, 20.0],
            executed_times_s={
                "A1": 5.0,
                "A2": 3.5,
                "A3": 0.0,
            },
            completed_wells=["A1"],
            stage_only=False,
            current_percents=[30, 55, 0],
            last_laser_off_confirmed=True,
            state=ExperimentState.STOPPED,
        )

    def test_report_classifies_each_well(self) -> None:
        rows = build_run_rows(self.make_runner())

        self.assertEqual(
            [row["outcome"] for row in rows],
            ["completed", "partial", "not_started"],
        )
        self.assertEqual(
            [row["completion_percent"] for row in rows],
            ["100.0", "35.0", "0.0"],
        )
        self.assertEqual(
            [row["execution_mode"] for row in rows],
            ["irradiation", "irradiation", "sham_0_percent"],
        )
        self.assertEqual(
            [row["programmed_current_percent"] for row in rows],
            [30, 55, 0],
        )
        self.assertTrue(all(row["final_laser_off_confirmed"] == "yes" for row in rows))

    def test_csv_report_is_written_with_expected_content(self) -> None:
        runner = self.make_runner()

        with tempfile.TemporaryDirectory() as directory:
            report_path = write_csv_report(directory, runner)

            self.assertEqual(
                report_path,
                Path(directory) / "run_summary.csv",
            )
            self.assertTrue(report_path.exists())

            with report_path.open(
                "r",
                encoding="utf-8",
                newline="",
            ) as file:
                reader = csv.DictReader(file)
                rows = list(reader)

            self.assertEqual(reader.fieldnames, FIELDNAMES)
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[0]["well"], "A1")
            self.assertEqual(rows[0]["executed_duration_s"], "5.000")
            self.assertEqual(rows[1]["well"], "A2")
            self.assertEqual(rows[1]["executed_duration_s"], "3.500")
            self.assertEqual(rows[2]["well"], "A3")
            self.assertEqual(rows[2]["execution_mode"], "sham_0_percent")

    def test_stage_only_report_marks_laser_as_not_applicable(self) -> None:
        runner = self.make_runner()
        runner.stage_only = True

        rows = build_run_rows(runner)

        self.assertTrue(all(row["execution_mode"] == "stage_only" for row in rows))
        self.assertTrue(all(row["programmed_current_percent"] == "" for row in rows))
        self.assertTrue(
            all(row["final_laser_off_confirmed"] == "not_applicable" for row in rows)
        )


if __name__ == "__main__":
    unittest.main()
