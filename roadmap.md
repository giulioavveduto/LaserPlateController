# LaserPlateController Roadmap

## Goal

Develop a reliable desktop application for automated laser exposure of multiwell plates using a programmable XY stage.

## Milestone 1 — Project foundation

- [x] Create Python/PySide6 application
- [x] Configure Git and GitHub repository
- [x] Separate stage operations from the GUI
- [x] Implement clean worker-thread shutdown

## Milestone 2 — Stage control

- [x] Implement real DMSTC stage backend
- [x] Implement simulated stage backend
- [x] Connect and disconnect the stage
- [x] Manual relative and absolute movement
- [x] Homing
- [x] Display stage position
- [x] Disable incompatible controls while moving
- [ ] Validate operation extensively with physical hardware

## Milestone 3 — Plate geometry and calibration

- [x] Support plate definitions and well coordinates
- [x] Display selectable plate wells
- [x] Save persistent A1 calibration by plate type
- [x] Convert well positions into stage coordinates
- [x] Navigate to one selected well
- [x] Disable navigation when its prerequisites are not satisfied
- [ ] Add movement-boundary and plate-orientation safety checks

## Milestone 4 — Protocol design

- [x] Select wells
- [x] Define a common exposure time
- [x] Validate protocol completeness
- [x] Estimate total exposure duration
- [x] Save protocols
- [x] Open and restore protocols
- [x] Reset stale protocol state after changing plate type
- [ ] Define or confirm deterministic well execution order

## Milestone 5 — Experiment execution

- [x] Define the initial ExperimentRunner state model
- [ ] Snapshot a valid protocol when execution starts
- [ ] Enable Start only when all prerequisites are satisfied
- [ ] Move automatically between selected wells
- [ ] Run the exposure timer at each well
- [ ] Display current well
- [ ] Display remaining time
- [ ] Complete an experiment cleanly
- [ ] Stop an experiment safely
- [ ] Handle movement and execution errors
- [ ] Add pause and resume if required

## Milestone 6 — Laser integration and safety

- [ ] Define the laser-control interface
- [ ] Integrate laser triggering
- [ ] Guarantee laser-off behaviour during movement and errors
- [ ] Add emergency-stop behaviour
- [ ] Add configurable safety limits and interlocks
- [ ] Record exposure events and failures

## Milestone 7 — Validation and distribution

- [ ] Add automated tests for protocol and runner logic
- [ ] Test simulator workflows
- [ ] Validate positioning accuracy and repeatability
- [ ] Validate complete experiments with the physical stage
- [ ] Add structured experiment logs
- [ ] Package the application for Windows
- [ ] Write installation and operating documentation
