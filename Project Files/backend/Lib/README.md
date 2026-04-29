# Lib

Core libraries used by the backend. Imported as `Lib.X` from `app.py`, `main.py`, and `RoomNav.py`.

| Module | Purpose |
| --- | --- |
| `BirdBrain.py` | Vendored BirdBrain Technologies Python driver for the Finch 2.0 / Hummingbird Bit. Talks to the robot through the BlueBird Connector. Not modified — see `BiraBrainREADME.md` for the upstream README. |
| `RoomFinch.py` | Wrapper around `BirdBrain.Finch` that adds pose tracking, PID-based motion (heading-hold forward + closed-loop turns), wall-position projection, temperature averaging, and a tail-LED temperature display thread. The `usePID` flag toggles between PID and the legacy blocking BirdBrain calls at runtime. |
| `PidController.py` | `PIDFinchController` — encoder-driven PID for `driveStraight`, `turnTo`, and continuous `holdHeadingStep`. Computes heading from encoder differentials so it survives a broken compass. |
| `RoomMap.py` | `Room_Map` — accumulates wall anchors, persists them to `anchors.csv`, and broadcasts each new anchor through a module-level pub/sub (`register_anchor_listener` / `_notify_anchor`) so the SocketIO layer can stream them to the frontend. |

## Adding a listener

`RoomMap` exposes a small pub/sub for anchor additions so multiple consumers (the SocketIO push, future on-disk snapshotters, etc.) can react without `Room_Map` knowing about them:

```python
from Lib.RoomMap import register_anchor_listener

def on_new_anchor(anchor):
    print("new wall anchor:", anchor)

register_anchor_listener(on_new_anchor)
```

Listeners fire after the anchor is appended to `anchorList` and written to `anchors.csv`. Exceptions raised by listeners are swallowed and logged so a misbehaving subscriber can't take down navigation.
