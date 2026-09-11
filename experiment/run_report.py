from __future__ import annotations

import csv
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from experiment.experiment_runner import ExperimentRunner


FIELDNAMES = [
    "sequence",
    "well",
    "outcome",
    "planned_duration_s",
    "executed_duration_s",
    "completion_percent",
    "programmed_current_percent",
    "execution_mode",
    "terminal_state",
    "final_laser_off_confirmed",
]


def build_run_rows(
    runner: ExperimentRunner,
) -> list[dict[str, object]]:
    completed = set(runner.completed_wells)
    rows: list[dict[str, object]] = []

    for index, well in enumerate(runner.wells):
        planned_s = runner.exposure_times_s[index]
        executed_s = min(
            planned_s,
            max(0.0, runner.executed_times_s.get(well, 0.0)),
        )

        if well in completed:
            outcome = "completed"
        elif executed_s <= 0.0:
            outcome = "not_started"
        elif executed_s < planned_s:
            outcome = "partial"
        else:
            outcome = "duration_elapsed_not_completed"

        if runner.stage_only:
            current_percent: int | str = ""
            execution_mode = "stage_only"
            final_off: str = "not_applicable"
        else:
            current_percent = runner.current_percents[index]
            execution_mode = "sham_0_percent" if current_percent == 0 else "irradiation"
            final_off = "yes" if runner.last_laser_off_confirmed else "no"

        completion_percent = (
            0.0 if planned_s <= 0.0 else min(100.0, 100.0 * executed_s / planned_s)
        )

        rows.append(
            {
                "sequence": index + 1,
                "well": well,
                "outcome": outcome,
                "planned_duration_s": f"{planned_s:.3f}",
                "executed_duration_s": f"{executed_s:.3f}",
                "completion_percent": f"{completion_percent:.1f}",
                "programmed_current_percent": current_percent,
                "execution_mode": execution_mode,
                "terminal_state": runner.state.name,
                "final_laser_off_confirmed": final_off,
            }
        )

    return rows


def write_csv_report(
    run_directory: str | Path,
    runner: ExperimentRunner,
) -> Path:
    directory = Path(run_directory)
    directory.mkdir(parents=True, exist_ok=True)

    report_path = directory / "run_summary.csv"

    with report_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=FIELDNAMES,
        )
        writer.writeheader()
        writer.writerows(build_run_rows(runner))

    return report_path
