from __future__ import annotations

import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication

from experiment.experiment_protocol import (
    ExperimentProtocol,
    LaserSetpoint,
)
from experiment.experiment_runner import (
    ExperimentRunner,
    ExperimentState,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class AutomaticLaser:
    """Immediately returns successful replies to runner commands."""

    def __init__(self, runner: ExperimentRunner) -> None:
        self.runner = runner
        self.enabled = False
        self.percent = 0
        self.commands: list[tuple[str, int]] = []

        runner.laser_requested.connect(self.handle_request)

    def handle_request(
        self,
        token: int,
        action: str,
        value: int,
        cancel_event: object,
    ) -> None:
        self.commands.append((action, value))

        if action == "off":
            self.enabled = False
        elif action == "current":
            self.percent = value
        elif action == "on":
            self.percent = value
            self.enabled = True

        self.runner.notify_laser_finished(
            token,
            self.enabled,
            self.percent,
            "",
        )


def make_protocol(
    wells: list[str],
    *,
    duration_s: float = 10.0,
    current_percent: int = 30,
) -> ExperimentProtocol:
    return ExperimentProtocol(
        name="Regression test",
        plate_type="96-well plate",
        selected_wells=wells,
        common_exposure_time_s=duration_s,
        default_laser_setpoint=LaserSetpoint(
            mode="current_percent",
            value=float(current_percent),
        ),
    )


class ExperimentRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = (
            QCoreApplication.instance()
            or QCoreApplication([])
        )

    def setUp(self) -> None:
        self.clock = FakeClock()
        self.clock_patch = patch(
            "experiment.experiment_runner.time.monotonic",
            self.clock.monotonic,
        )
        self.clock_patch.start()

    def tearDown(self) -> None:
        self.clock_patch.stop()

    def test_pause_excludes_paused_time_and_resume_completes(self) -> None:
        runner = ExperimentRunner()
        laser = AutomaticLaser(runner)
        homes: list[bool] = []

        runner.home_requested.connect(lambda: homes.append(True))

        runner.start(
            make_protocol(["A1"]),
            stage_only=False,
        )
        self.assertEqual(runner.state, ExperimentState.MOVING)

        runner.notify_movement_finished()
        self.assertEqual(runner.state, ExperimentState.EXPOSING)

        self.clock.advance(3.5)
        runner.pause()

        self.assertEqual(runner.state, ExperimentState.PAUSED)
        self.assertAlmostEqual(
            runner.executed_times_s["A1"],
            3.5,
            places=6,
        )
        self.assertFalse(laser.enabled)

        self.clock.advance(50.0)
        runner.resume()

        self.assertEqual(runner.state, ExperimentState.EXPOSING)
        self.assertTrue(laser.enabled)

        self.clock.advance(6.5)
        runner._update_exposure()

        self.assertEqual(runner.state, ExperimentState.HOMING)
        self.assertEqual(len(homes), 1)
        self.assertFalse(laser.enabled)

        runner.notify_homing_finished()

        self.assertEqual(runner.state, ExperimentState.COMPLETED)
        self.assertAlmostEqual(
            runner.executed_times_s["A1"],
            10.0,
            places=6,
        )
        self.assertTrue(runner.last_laser_off_confirmed)

    def test_zero_percent_well_remains_off(self) -> None:
        runner = ExperimentRunner()
        laser = AutomaticLaser(runner)
        protocol = make_protocol(
            ["A1", "A2"],
            duration_s=5.0,
            current_percent=30,
        )

        protocol.set_exposure_time_for_wells(["A2"], 7.0)
        protocol.set_laser_setpoint_for_wells(
            ["A2"],
            LaserSetpoint(
                mode="current_percent",
                value=0.0,
            ),
        )

        runner.start(protocol, stage_only=False)

        runner.notify_movement_finished()
        self.assertTrue(laser.enabled)

        self.clock.advance(5.0)
        runner._update_exposure()

        self.assertEqual(runner.current_well, "A2")
        self.assertEqual(runner.state, ExperimentState.MOVING)
        self.assertFalse(laser.enabled)

        runner.notify_movement_finished()

        self.assertEqual(runner.state, ExperimentState.EXPOSING)
        self.assertFalse(laser.enabled)

        self.clock.advance(7.0)
        runner._update_exposure()

        self.assertEqual(runner.state, ExperimentState.HOMING)
        runner.notify_homing_finished()

        self.assertEqual(runner.state, ExperimentState.COMPLETED)
        self.assertEqual(runner.completed_wells, ["A1", "A2"])
        self.assertEqual(
            [
                command
                for command in laser.commands
                if command[0] == "on"
            ],
            [("on", 30)],
        )

    def test_stop_during_movement_waits_then_homes(self) -> None:
        runner = ExperimentRunner()
        laser = AutomaticLaser(runner)
        homes: list[bool] = []

        runner.home_requested.connect(lambda: homes.append(True))

        runner.start(
            make_protocol(["B2"]),
            stage_only=False,
        )
        self.assertEqual(runner.state, ExperimentState.MOVING)

        runner.request_stop()

        self.assertEqual(runner.state, ExperimentState.STOPPING)
        self.assertEqual(homes, [])

        runner.notify_movement_finished()

        self.assertEqual(len(homes), 1)
        self.assertFalse(laser.enabled)

        runner.notify_homing_finished()

        self.assertEqual(runner.state, ExperimentState.STOPPED)
        self.assertTrue(runner.last_laser_off_confirmed)
        self.assertNotIn(("on", 30), laser.commands)

    def test_stage_failure_forces_off_and_latches_fault(self) -> None:
        runner = ExperimentRunner()
        laser = AutomaticLaser(runner)
        homes: list[bool] = []
        errors: list[str] = []
        protocol = make_protocol(["C3"])

        runner.home_requested.connect(lambda: homes.append(True))
        runner.error_occurred.connect(errors.append)

        runner.start(protocol, stage_only=False)
        self.assertEqual(runner.state, ExperimentState.MOVING)

        runner.fail("Simulated stage failure")

        self.assertEqual(runner.state, ExperimentState.ERROR)
        self.assertTrue(runner.fault_latched)
        self.assertTrue(runner.last_laser_off_confirmed)
        self.assertFalse(laser.enabled)
        self.assertEqual(homes, [])
        self.assertIn("Simulated stage failure", errors[-1])

        with self.assertRaises(RuntimeError):
            runner.start(protocol, stage_only=False)

    def test_timeout_attempts_second_off_and_blocks_movement(self) -> None:
        runner = ExperimentRunner()
        commands: list[tuple[int, str, int]] = []
        moves: list[str] = []
        errors: list[str] = []

        runner.laser_requested.connect(
            lambda token, action, value, cancel:
            commands.append((token, action, value))
        )
        runner.move_requested.connect(moves.append)
        runner.error_occurred.connect(errors.append)

        runner.start(
            make_protocol(["D4"]),
            stage_only=False,
        )

        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0][1:], ("off", 0))

        runner._on_laser_timeout()

        self.assertEqual(len(commands), 2)
        self.assertEqual(commands[1][1:], ("off", 0))
        self.assertEqual(moves, [])
        self.assertTrue(runner.fault_latched)

        runner._on_laser_timeout()

        self.assertEqual(runner.state, ExperimentState.ERROR)
        self.assertFalse(runner.last_laser_off_confirmed)
        self.assertEqual(moves, [])
        self.assertIn(
            "physical safety key",
            errors[-1].lower(),
        )


if __name__ == "__main__":
    unittest.main()