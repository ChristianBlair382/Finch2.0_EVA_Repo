# Basic Function Scripts

Standalone sanity-check scripts for the Finch 2.0 hardware. Each script imports `BirdBrain.Finch` directly (not the `RoomFinch` wrapper) and exercises one subsystem in isolation. Useful for verifying that a freshly-paired Finch is healthy before running the full `app.py` / `navigateRoom` stack.

The Finch must be paired through the **BlueBird Connector** before any of these will run.

| Script | What it does |
| --- | --- |
| `FinchTest.py` | Sound + beak LED smoke test: plays a note then cycles the beak LED. |
| `Finch_InfraredSensor_Test.py` | Prints a single front-distance reading from the IR sensor. |
| `Finch_LEDArrayTest.py` | Scrolls "hello" across the 5×5 micro:bit LED matrix. |
| `Finch_Movement_Test.py` | Demonstrates motor primitives — turns and short forward moves. |
| `Finch_SoundTest.py` | Sweeps notes 32–135 to verify the speaker. |
| `manual.py` | WASD-style keyboard control loop using the `keyboard` package. Predates the SocketIO frontend's manual mode. |
| `meow.py` | Tiny demo sequence — moves, turns, plays notes. |

## Non-script reference

| File | Purpose |
| --- | --- |
| `Odometry.txt` | Snippet of an `updateMotorOdometry` method retained as a reference for motor-only pose estimation. Not imported anywhere. |

To run any script:

```powershell
cd "Project Files/backend/Basic Function Scripts"
python FinchTest.py
```

Note that these scripts default to Finch port `A` unless you edit them — `meow.py` is on port `B` for example.
