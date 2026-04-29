# Backend

Python backend for the Room Mapper. Drives the Finch 2.0 (via the BlueBird Connector) and exposes a Flask-SocketIO API consumed by the React frontend.

## Layout

| Path | Purpose |
| --- | --- |
| `app.py` | Flask-SocketIO server. Main entry point when running with the web frontend. Listens on `:5000` and emits `map_update` / `status_update` events. |
| `main.py` | Standalone CLI entry point. Lets the user pick manual control or auto navigation without a frontend. |
| `RoomNav.py` | `navigateRoom(finch, stop_event=None)` (right-wall-following auto nav) and `ManualController` (button-driven manual mode). |
| `Lib/` | Core libraries: `RoomFinch`, `PidController`, `RoomMap`, and the vendored `BirdBrain` driver. See `Lib/README.md`. |
| `Basic Function Scripts/` | Standalone hardware sanity-check scripts for the Finch (motors, sensors, LEDs, audio). See that folder's README. |
| `tests/` | Backend pytest tests. |
| `test_heading.py`, `test_pid.py` | Hardware-in-the-loop scripts that exercise the PID/heading code on a real Finch. Not part of the pytest suite. |
| `requirements.txt` | Python dependencies (Flask, Flask-SocketIO, python-socketio). |
| `anchors.csv`, `path.csv`, `room_map.json` | Per-session map artefacts written by `app.py` at runtime; safe to delete. |

## Running

The Finch must be paired and connected through the **BlueBird Connector** desktop app on port A before either entry point will start (the constructor blocks until the BLE link is up).

```powershell
python -m pip install -r requirements.txt
python app.py        # Flask-SocketIO server, used with the frontend
# or
python main.py       # standalone CLI menu
```

`app.py` runs on `http://127.0.0.1:5000` and accepts cross-origin connections so the Vite dev server (default `:5173`) can connect to it directly.

## Socket interface

Frontend → backend, single event `command` carrying one of:
`start`, `stop`, `reset`, `scan_anchor`, `up`, `down`, `left`, `right`, `load_map`.

Backend → frontend:
- `map_update`: `{ grid, robot, path, raw_path, anchors, temperature, light }`
- `status_update`: `{ status }`

See the docstring at the top of `app.py` for the full contract.

## Tuning

The Finch behaves differently on different surfaces — carpet, hardwood, tile, vinyl, and concrete each change wheel slip, traction, and turn accuracy. Before running, the constants below should be tuned to the floor the robot is on. Symptoms of an untuned robot include drifting heading during straight runs, over- or under-shooting 90° turns, stalling mid-motion, and accumulating positional error after just a few corners.

All of the values discussed below live in `Lib/PidController.py` and `Lib/RoomFinch.py`. Restart `app.py` after changing them.

### 1. Wheelbase (most impactful)

The kinematic formula in `EncoderHeading` derives chassis rotation from the difference in left/right encoder ticks divided by the wheelbase. Carpet causes the wheels to slip and *over-count*, so a larger effective wheelbase compensates by reporting less heading change per tick.

Edit the constructor call inside `PIDFinchController.__init__` in `Lib/PidController.py`:

```python
# default — slick floors (hardwood, tile, vinyl)
self._compass = compassAverage or EncoderHeading(finch, wheelbase_cm=10.5)

# carpet — compensates for ~12% encoder over-count from wheel slip
self._compass = compassAverage or EncoderHeading(finch, wheelbase_cm=11.8)
```

Rule of thumb: if 90° turns consistently *under-rotate* (the robot stops short of a true right angle), increase `wheelbase_cm` in 0.3 cm steps. If turns *over-rotate*, decrease it.

### 2. Turn scale

`RoomFinch.turnScale` is a multiplier applied to every commanded turn angle (`turnLeft`, `turnRight`, `turnToHeading`). It compensates for systematic offsets that aren't fully absorbed by the wheelbase fix.

Two options:

- **Manual** — set it once at startup by editing `self.turnScale = 1.0` in `RoomFinch.__init__` (`Lib/RoomFinch.py`), or call `finch.setTurnScale(<value>)` at runtime. `main.py` exposes choice 3 ("Set Turn Scale Manually") for this.
- **Auto** — call `finch.calibrateFloor()` with the robot facing a wall. It rotates a full 360° while sampling distances and computes `turnScale = turn_count / 36`.

Rule of thumb: start at `1.0`; raise toward `1.1`–`1.2` on carpet if turns under-rotate even after wheelbase tuning; lower toward `0.9` on slick surfaces if turns over-rotate.

### 3. PID gains (Kp, Ki, Kd)

Three independent PID loops run inside `PIDFinchController` (`Lib/PidController.py`). Their default gains are at the top of the class:

```python
DEFAULT_HEADING_GAINS = (0.8, 0.02, 0.4)   # heading-hold while driving forward
DEFAULT_TURN_GAINS    = (0.3, 0.0,  0.15)  # turn-in-place to a heading
DEFAULT_DRIVE_GAINS   = (4.0, 0.0,  0.5)   # distance ramp for driveStraight
```

Each gain has a different role:

- **Kp (proportional)** — how aggressively the controller reacts to the current error. Too low: sluggish, never reaches target. Too high: overshoots, oscillates, wobbles.
- **Ki (integral)** — accumulates persistent error to fight steady-state bias (e.g. one motor weaker than the other). Too low: the robot drifts off heading without correcting. Too high: integral wind-up, oscillation, slow recovery.
- **Kd (derivative)** — damps overshoot by reacting to *rate of change* of the error. Higher Kd = cleaner stop, less wobble at the end of a turn. Too high: amplifies sensor noise into jitter.

Tuning recipe (Ziegler-Nichols-lite, applied per loop):

1. Set `Ki = 0` and `Kd = 0`.
2. Increase `Kp` until the robot just starts to oscillate around the target on a typical command (a 90° turn, or a 60 cm cruise).
3. Halve that `Kp`. Then increase `Kd` until oscillation is damped without making motion sluggish.
4. Add a small `Ki` (start at `0.01` for heading, `0` for turns/drives) only if you see persistent steady-state bias that `Kp + Kd` doesn't eliminate.

Tune one loop at a time. Heading-hold gains affect straight-line drift; turn gains affect 90° turn cleanness; drive gains affect how forcefully `driveStraight` ramps down on approach.

### 4. Stiction floor (`MIN_MOTOR_OUTPUT`)

Below a certain motor command, the wheels won't break static friction from rest. Defined in `PidController.py`:

```python
MIN_MOTOR_OUTPUT = 8
```

- **Lower** (e.g. `5`) on slick floors — lets the PID ramp down to a smaller command before stopping, giving cleaner approaches.
- **Raise** (e.g. `12`) on carpet — keeps the PID above the surface's friction floor so motion doesn't stall mid-correction.

If the robot stalls just before reaching its target heading (turn ends 1–2° short and never closes the gap), raise `MIN_MOTOR_OUTPUT`.

### 5. Speed and output limits (advanced)

The remaining tunables in `PidController.py` cap how aggressively each PID loop drives the motors:

| Constant | Role | Default |
| --- | --- | --- |
| `TURN_OUTPUT_LIMIT` | Max wheel speed during a turn-in-place | 15 |
| `HEADING_OUTPUT_LIMIT` | Max steering differential during cruise | 12 |
| `DRIVE_HEADING_OUTPUT_LIMIT` | Max steering differential during `driveStraight` | 12 |
| `DEFAULT_DRIVE_BASE_SPEED` | Forward speed for `driveStraight` | 30 |
| `DEFAULT_CRUISE_BASE_SPEED` | Forward speed for `holdHeadingStep` cruise | 24 |
| `TURN_TOLERANCE_DEG` | Turn exits within ±this of target | 2.0 |
| `DRIVE_TOLERANCE_CM` | Drive exits within ±this of target | 0.5 |

Lower the speed values for gentler motion (useful when first dialling in a new surface). Loosen the tolerance values if the PID is hunting at the end of every motion and never quite settling — but if you raise them too much, position error compounds across many corners.

### 6. Quick reference: what to change for what symptom

| Symptom | First thing to try |
| --- | --- |
| Heading drifts during forward motion | Raise `Kp` in `DEFAULT_HEADING_GAINS`, or add a small `Ki` |
| 90° turns consistently under-rotate | Increase `wheelbase_cm` (or `turnScale`) |
| 90° turns consistently over-rotate | Decrease `wheelbase_cm` (or `turnScale`) |
| Robot stalls before completing a turn | Raise `MIN_MOTOR_OUTPUT`, or lower `TURN_TOLERANCE_DEG` |
| Robot oscillates around target heading | Lower `Kp` and/or raise `Kd` in the relevant `*_GAINS` tuple |
| Position error compounds over many corners | Re-run `calibrateFloor()` and fine-tune `wheelbase_cm` |
| Motion is too aggressive / unsafe | Lower `DEFAULT_CRUISE_BASE_SPEED` and `TURN_OUTPUT_LIMIT` |
