# Project Status

Last updated: 2026-07-23  
Latest validated commit: `2bcdf8d`

## Current milestone

Implement simulator-safe experiment execution.

## Working features

- Real and simulated stage backends
- Stage connection, disconnection, movement and homing
- Clean stage-worker shutdown
- Plate definitions and graphical well selection
- Persistent A1 calibration by plate type
- Coordinate calculation from A1 calibration
- Navigation to one selected well
- Protocol exposure-time entry and validation
- Selected-well count and duration estimation
- Protocol save, open and restoration
- Correct protocol refresh after changing plate type
- Correct navigation refresh after connection, disconnection and movement

## Current implementation

`experiment/experiment_runner.py` has been replaced with a Qt-based state model.

Defined states:

- `IDLE`
- `MOVING`
- `EXPOSING`
- `COMPLETED`
- `STOPPED`
- `ERROR`

The runner currently stores:

- Ordered wells
- Current-well index
- Exposure duration
- Current experiment state

It also defines signals for state, current well, remaining time, completion and errors.

The runner is not yet connected to the GUI or stage.

## Last validation

Passed:

- `python -m py_compile main.py`
- `python -m compileall -q .`
- Plate changes clear the previous selection and invalidate the protocol
- Stage disconnection immediately disables well navigation
- Navigation is disabled during movement
- Navigation is restored after movement when its prerequisites remain valid
- Protocol save and restoration work
- Simulator navigation reaches the expected coordinates

## Known limitations

- Start Experiment is disabled
- No automatic well sequence
- No exposure countdown
- Current-well and remaining-time fields are placeholders
- No stop or pause execution logic
- No laser-control integration
- ExperimentRunner has not yet been tested through the GUI

## Next step

Add `start()` and protocol snapshotting to `ExperimentRunner`.

Then connect Start-button eligibility to:

- Valid protocol
- Connected stage
- Idle stage
- Available A1 calibration for the selected plate
- Idle experiment runner

Initial execution tests must use the simulator.

## Architectural decisions

- `ExperimentRunner` owns experiment state, sequence progression and timing.
- `MainWindow` owns stage connectivity and well-to-stage coordinate conversion.
- The protocol is snapshotted at experiment start so GUI edits cannot modify a running experiment.
- The first execution implementation will use the simulator.
- Laser integration will occur only after movement and timing behaviour are validated.
- `PROJECT_STATUS.md` is updated at each validated development checkpoint.
- `ROADMAP.md` is updated only when milestones or project scope change.
