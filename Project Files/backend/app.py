"""Flask-SocketIO backend for the RoomFinch web frontend.

Frontend interface (preserved from previous app.py — App.tsx already speaks
this dialect, don't change it without coordinating):
  frontend -> backend:
      'command'        : one of 'start','stop','reset','scan_anchor',
                                 'up','down','left','right'
  backend  -> frontend:
      'map_update'     : { grid, robot, path, temperature, light }
      'status_update'  : { status }

Internally:
  - Manual commands route through ManualController so anchors land in the
    same CSV/format used by auto nav, with the same step sizes.
  - Auto nav (navigateRoom) is kicked off as a SocketIO background task.
  - Live position pushes are wired through RoomFinch.register_position_callback
    rather than manual update_position() calls after each command.
"""
import csv
import json
from threading import Event, Lock

from flask import Flask
from flask_socketio import SocketIO

from Lib.RoomFinch import RoomFinch
from Lib.RoomMap import register_anchor_listener
from RoomNav import navigateRoom, ManualController


# ------------------------------
# Web app / socket setup
# ------------------------------
app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins='*')

GRID_SIZE = 20

# usePID=True per the new RoomFinch architecture: PID heading-hold during
# forward motion plus closed-loop turns. setUsePID(False) at runtime to
# fall back to the legacy blocking BirdBrain calls without restarting if
# PID misbehaves.
finch = RoomFinch('A', usePID=True)

# ManualController owns its own Room_Map and resets anchors.csv on
# construction — that gives every backend startup a clean per-session map.
controller = ManualController(finch)


# ---------------------------------------------------------------------------
# Frontend-facing state
# ---------------------------------------------------------------------------
# Shape mirrors what App.tsx's 'map_update' handler expects.
#
# CAVEAT: positions from RoomFinch are in cm but the frontend grid is a
# fixed 20x20, so a clamp is applied. For rooms larger than ~20 cm the
# clamp must be replaced with a rescale (e.g.
# cell = int(x_cm * GRID_SIZE / ROOM_WIDTH_CM)) in _on_position_changed
# below — the original clamp behaviour is kept for now to match the
# frontend that just merged.
state = {
    'grid': [[0 for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)],
    'robot': {'x': 0, 'y': 0},
    # path / raw_path start empty — the seed (0,0) used to anchor the chart
    # at the origin before any real motion, but it created a phantom data
    # point at startup. Now they only contain entries pushed by the
    # position callback once the robot actually reports a pose.
    'path': [],
    # raw_path mirrors path but in cm — the Room Map chart on the frontend
    # plots it together with anchors so both share a coordinate scale. The
    # clamped 0..GRID_SIZE-1 path is still useful for the grid panel but
    # would visually flatten any real-room anchors plotted alongside it.
    'raw_path': [],
    # anchors is the live mirror of anchors.csv: wall positions written by
    # Room_Map.add_anchor / add_anchor_at_position. Pushed to the frontend
    # via map_update so the chart can render the room outline.
    'anchors': [],
    'temperature': 0,
    # Light sensors are non-functional on this hardware (see RoomFinch
    # docstring). Kept at 0 so App.tsx's telemetry panel doesn't break.
    'light': 0,
}

# Serialize state mutations: the position callback fires from the motion
# thread (manual commands) or the auto-nav background task, while
# reset_state runs on the SocketIO handler thread.
_state_lock = Lock()


# ---------------------------------------------------------------------------
# Map persistence — path.csv + room_map.json
# ---------------------------------------------------------------------------
# anchors.csv is owned by Lib.RoomMap (written line-by-line as each anchor is
# created). Below we mirror the same pattern for the trajectory:
#   - path.csv: appended to in _on_position_changed, one row per pose update
#   - room_map.json: a combined snapshot of {path, anchors} written after
#     every state change. This is the file the frontend's Load Map button
#     uploads to round-trip a saved session.
PATH_CSV = 'path.csv'
ANCHORS_CSV = 'anchors.csv'
MAP_JSON = 'room_map.json'


def _reset_path_csv():
    """Truncate path.csv with a fresh x,y header. Mirrors the lifecycle of
    anchors.csv (which Room_Map clears at session start)."""
    with open(PATH_CSV, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['x', 'y'])


def _append_path_csv(x, y):
    with open(PATH_CSV, 'a', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([x, y])


def _save_map_json():
    """Write the live (path + anchors) snapshot to room_map.json. Called
    on every state change so the file always reflects current state.
    Cheap enough at this scale.
    """
    snapshot = {
        'path': state['raw_path'],
        'anchors': state['anchors'],
    }
    with open(MAP_JSON, 'w') as f:
        json.dump(snapshot, f, indent=2)


# Initialise path.csv at backend startup so a file from a previous
# session doesn't bleed into this one. anchors.csv is reset by ManualController
# / navigateRoom on their own.
_reset_path_csv()
_save_map_json()


def emit_map_update():
    socketio.emit('map_update', state)


def reset_state():
    with _state_lock:
        state['grid'] = [[0 for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
        state['robot'] = {'x': 0, 'y': 0}
        # Match the empty seeding in the initial state — see comment there.
        state['path'] = []
        state['raw_path'] = []
        state['anchors'] = []
        state['temperature'] = 0
        state['light'] = 0
    _reset_path_csv()
    with open(ANCHORS_CSV, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['x', 'y'])
    _save_map_json()
    emit_map_update()


def _on_position_changed(x, y, heading):
    """RoomFinch position-callback subscriber. Fires after every motion
    that updates the robot's pose, from whatever thread did the motion.
    Pushes a 'map_update' so App.tsx redraws and persists the new pose
    to path.csv + room_map.json."""
    with _state_lock:
        gx = max(0, min(GRID_SIZE - 1, int(x)))
        gy = max(0, min(GRID_SIZE - 1, int(y)))
        state['robot'] = {'x': gx, 'y': gy}
        state['path'].append({'x': gx, 'y': gy})
        if len(state['path']) > 500:
            state['path'] = state['path'][-500:]
        state['raw_path'].append({'x': float(x), 'y': float(y)})
        if len(state['raw_path']) > 500:
            state['raw_path'] = state['raw_path'][-500:]
        state['grid'][gy][gx] = 1
        # Live current temp, not session average
        state['temperature'] = round(finch.getCurrentTemperature(), 2)
    _append_path_csv(float(x), float(y))
    _save_map_json()
    emit_map_update()


def _on_anchor_added(anchor):
    """Room_Map listener — called once per wall anchor, regardless of
    whether it came from auto-nav (navigateRoom) or manual scan
    (ManualController.scan_anchor). Mirrors the (x, y) into the SocketIO
    state so the frontend chart can plot the room outline live, and
    refreshes the room_map.json snapshot."""
    ax, ay = float(anchor[0]), float(anchor[1])
    with _state_lock:
        state['anchors'].append({'x': ax, 'y': ay})
        # Keep memory bounded — a long auto-nav run can drop hundreds.
        if len(state['anchors']) > 1000:
            state['anchors'] = state['anchors'][-1000:]
    _save_map_json()
    emit_map_update()


finch.register_position_callback(_on_position_changed)
register_anchor_listener(_on_anchor_added)


# ---------------------------------------------------------------------------
# Auto-nav worker
# ---------------------------------------------------------------------------
# _auto_stop_event is the cooperative shutdown signal threaded through
# navigateRoom(finch, stop_event=...). Setting it makes the nav loop break
# out at its next iteration boundary; finch.stop() is called alongside to
# interrupt whatever motor command is currently in flight. Any path that
# wants auto-nav to end (the 'stop'/'reset' buttons, or *any* manual
# command — manual override should pre-empt auto-nav) goes through
# _halt_auto_nav() below.
_auto_thread = None
_auto_stop_event = Event()


def auto_navigation_worker():
    try:
        navigateRoom(finch, stop_event=_auto_stop_event)
    except Exception as e:
        # Swallow & report so the SocketIO server keeps running even if
        # navigation crashes mid-run. The frontend gets a status update
        # so the user knows something went wrong.
        print(f"[auto-nav] worker raised: {e}")
        socketio.emit('status_update', {'status': f'auto nav error: {e}'})
        return
    if _auto_stop_event.is_set():
        socketio.emit('status_update', {'status': 'automatic navigation halted'})
    else:
        socketio.emit('status_update', {'status': 'automatic navigation complete'})


def _halt_auto_nav(timeout=2.0):
    """Signal the auto-nav worker to stop and wait briefly for it to exit.

    Idempotent — safe to call when no worker is running. Returns True if
    the worker is no longer alive (or never was), False if it's still
    going after the timeout. Caller is responsible for any state cleanup
    after this returns.
    """
    global _auto_thread
    thread = _auto_thread
    if thread is not None and thread.is_alive():
        _auto_stop_event.set()
        # Interrupt any in-flight motor command so the nav loop reaches
        # its next iteration check promptly instead of blocking on a
        # BIG_STEP cruise.
        finch.stop()
        thread.join(timeout=timeout)
        still_alive = thread.is_alive()
    else:
        still_alive = False
    if not still_alive:
        _auto_thread = None
    return not still_alive


# ---------------------------------------------------------------------------
# Socket handlers
# ---------------------------------------------------------------------------
@socketio.on('connect')
def handle_connect():
    print("Client connected")
    emit_map_update()


@socketio.on('disconnect')
def handle_disconnect():
    print("Client disconnected")


@socketio.on('load_map')
def handle_load_map(payload):
    """Replace the live room map with the contents of an uploaded file.

    Expected payload shape (matches the room_map.json this backend writes):
        { "path":    [ {"x": <cm>, "y": <cm>}, ... ],
          "anchors": [ {"x": <cm>, "y": <cm>}, ... ] }

    Extras in the payload are ignored; missing keys default to []. After
    replacing in-memory state, both anchors.csv and path.csv are rewritten
    to match so future appends stay coherent with the loaded data.

    Note: this only restores the *map* — it does not move the robot or
    affect navigation state. Auto-nav and manual control will continue to
    work from wherever the Finch physically is.
    """
    if not isinstance(payload, dict):
        socketio.emit('status_update', {'status': 'load_map: payload must be an object'})
        return

    raw_path = payload.get('path') or []
    raw_anchors = payload.get('anchors') or []

    def _coerce_xy(items, label):
        out = []
        for i, item in enumerate(items):
            try:
                out.append({'x': float(item['x']), 'y': float(item['y'])})
            except (KeyError, TypeError, ValueError):
                raise ValueError(f"{label}[{i}] is not a valid {{x, y}} entry")
        return out

    try:
        loaded_raw_path = _coerce_xy(raw_path, 'path')
        loaded_anchors = _coerce_xy(raw_anchors, 'anchors')
    except ValueError as e:
        socketio.emit('status_update', {'status': f'load_map: {e}'})
        return

    with _state_lock:
        state['raw_path'] = loaded_raw_path
        # Rebuild the clamped grid path from raw_path so the grid panel
        # stays consistent with the trajectory chart.
        state['path'] = [
            {'x': max(0, min(GRID_SIZE - 1, int(p['x']))),
             'y': max(0, min(GRID_SIZE - 1, int(p['y'])))}
            for p in loaded_raw_path
        ]
        state['anchors'] = loaded_anchors
        # Repaint the visited grid from the loaded path.
        state['grid'] = [[0 for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
        for p in state['path']:
            state['grid'][p['y']][p['x']] = 1
        # Snap the robot icon to the last loaded pose, if any.
        if state['path']:
            state['robot'] = state['path'][-1]
        else:
            state['robot'] = {'x': 0, 'y': 0}

    # Rewrite the on-disk mirrors so a subsequent Reset followed by a
    # fresh run sees a clean state, and so room_map.json matches.
    _reset_path_csv()
    for p in state['raw_path']:
        _append_path_csv(p['x'], p['y'])
    with open(ANCHORS_CSV, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['x', 'y'])
        for a in state['anchors']:
            writer.writerow([a['x'], a['y']])
    _save_map_json()

    socketio.emit('status_update', {
        'status': f'map loaded: {len(state["raw_path"])} pose(s), '
                  f'{len(state["anchors"])} anchor(s)'
    })
    emit_map_update()


_MANUAL_COMMANDS = {'up', 'down', 'left', 'right', 'scan_anchor'}


@socketio.on('command')
def handle_command(command):
    """Multiplexed command entry — App.tsx emits 'command' with a string."""
    global _auto_thread
    print("Received command:", command)

    # --- auto nav ----------------------------------------------------
    if command == 'start':
        if _auto_thread is None or not _auto_thread.is_alive():
            # Clear the stop signal from any prior run before launching;
            # otherwise navigateRoom would exit on its first iteration.
            _auto_stop_event.clear()
            _auto_thread = socketio.start_background_task(auto_navigation_worker)
            socketio.emit('status_update', {'status': 'automatic navigation started'})
        else:
            socketio.emit('status_update', {'status': 'auto nav already running'})

    elif command == 'stop':
        # Real stop now: signal the nav loop AND halt current motion. The
        # worker's finalizer will emit 'automatic navigation halted'.
        if _halt_auto_nav():
            socketio.emit('status_update', {'status': 'stop signaled'})
        else:
            socketio.emit('status_update', {'status': 'stop signaled (worker still winding down)'})

    elif command == 'reset':
        _halt_auto_nav()
        reset_state()
        socketio.emit('status_update', {'status': 'state reset'})

    # --- manual mode -------------------------------------------------
    # Routed through ManualController so anchors land in the same CSV
    # used by auto nav. Position pushes happen automatically via the
    # registered callback; no explicit emit needed here.
    #
    # Manual commands ALSO pre-empt auto-nav: pressing any movement /
    # scan button while the auto worker is running halts it first, so
    # the two threads aren't fighting over the motor bus. This matches
    # the frontend's mental model where flipping to "Manual Navigation"
    # exits automatic mode.
    elif command in _MANUAL_COMMANDS:
        was_auto_running = _auto_thread is not None and _auto_thread.is_alive()
        if was_auto_running:
            _halt_auto_nav()
            socketio.emit('status_update', {'status': 'manual override — auto nav stopped'})

        if command == 'up':
            controller.forward()
        elif command == 'down':
            controller.backward()
        elif command == 'left':
            controller.left()
        elif command == 'right':
            controller.right()
        elif command == 'scan_anchor':
            controller.scan_anchor()

    else:
        socketio.emit('status_update', {'status': f'unknown command: {command}'})


if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)