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


`ExperimentRunner.start()` now:

- Rejects invalid protocols
- Prevents starting while already running
- Snapshots the plate type, selected wells and exposure time
- Sets the first current well
- Calculates the initial remaining exposure time
- Enters the `MOVING` state

The GUI now enables Start only when:

- The protocol is valid
- The stage is connected and idle
- The selected plate has an A1 calibration
- The experiment runner is not running

The Start button is not yet connected to automatic experiment execution.

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
- Runner protocol snapshot test passed
- Start eligibility responds to protocol, calibration and connection state
- Disconnecting the controller disables Start
- The interface remains accessible through a scrollable layout
- Normal stage disconnection is prevented while the stage is busy
- Start initializes the runner from a protocol snapshot
- Experiment state, current well and remaining time display correctly
- Start becomes disabled after runner initialization
- State-only initialization causes no stage or laser action

## Known limitations

- Start Experiment is disabled
- No automatic well sequence
- No exposure countdown
- Current-well and remaining-time fields are placeholders
- No stop or pause execution logic
- No laser-control integration
- ExperimentRunner has not yet been tested through the GUI
- Start does not yet trigger execution
- No automatic movement through selected wells
- No exposure countdown
- No stop or pause execution logic
- Movement-dependent states still require physical-stage validation
- The simulator completes movements immediately
- Optional asynchronous simulator movement delay is postponed
- No laser-control integration

## Next step

## Next step

Connect the runner's `MOVING` state to automatic movement toward the current well.

After the stage reports movement completion, transition to `EXPOSING` and start the exposure countdown. Laser control remains excluded.

## Architectural decisions

- `ExperimentRunner` owns experiment state, sequence progression and timing.
- `MainWindow` owns stage connectivity and well-to-stage coordinate conversion.
- The protocol is snapshotted at experiment start so GUI edits cannot modify a running experiment.
- The first execution implementation will use the simulator.
- Laser integration will occur only after movement and timing behaviour are validated.
- `PROJECT_STATUS.md` is updated at each validated development checkpoint.
- `ROADMAP.md` is updated only when milestones or project scope change.
