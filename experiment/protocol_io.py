from __future__ import annotations

import json
from pathlib import Path

from experiment.experiment_protocol import ExperimentProtocol


def save_protocol(
    protocol: ExperimentProtocol,
    file_path: str | Path,
) -> None:
    path = Path(file_path)

    path.write_text(
        json.dumps(protocol.to_dict(), indent=4),
        encoding="utf-8",
    )


def load_protocol(
    file_path: str | Path,
) -> ExperimentProtocol:
    path = Path(file_path)

    data = json.loads(
        path.read_text(encoding="utf-8")
    )

    if not isinstance(data, dict):
        raise ValueError("Protocol file must contain a JSON object.")

    return ExperimentProtocol.from_dict(data)