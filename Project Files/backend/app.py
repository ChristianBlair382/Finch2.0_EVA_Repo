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
from threading import Lock

from flask import Flask
from flask_socketio import SocketIO

from Lib.RoomFinch import RoomFinch
from RoomNav import navigateRoom, ManualController


# ---------------------------------------------------------------------------
# App / socket setup
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins='*')

GRID_SIZE = 20

# usePID=True per the new RoomFinch architecture: PID heading-hold during
# forward motion plus closed-loop turns. setUsePID(False) at runtime if it
# misbehaves and you want to fall back to the legacy blocking BirdBrain
# calls without restarting.
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
# fixed 20x20, so we clamp. For anything bigger than a ~20 cm room you'll
# want to rescale (e.g. cell = int(x_cm * GRID_SIZE / ROOM_WIDTH_CM)) in
# _on_position_changed below — leaving the original clamp behaviour for
# now to match the frontend that just merged.
state = {
    'grid': [[0 for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)],
    'robot': {'x': 0, 'y': 0},
    'path': [{'x': 0, 'y': 0}],
    'temperature': 0,
    # Light sensors are non-functional on this hardware (see RoomFinch
    # docstring). Kept at 0 so App.tsx's telemetry panel doesn't break.
    'light': 0,
}

# Serialize state mutations: the position callback fires from the motion
# thread (manual commands) or the auto-nav background task, while
# reset_state runs on the SocketIO handler thread.
_state_lock = Lock()


def emit_map_update():
    socketio.emit('map_update', state)


def reset_state():
    with _state_lock:
        state['grid'] = [[0 for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
        state['robot'] = {'x': 0, 'y': 0}
        state['path'] = [{'x': 0, 'y': 0}]
        state['temperature'] = 0
        state['light'] = 0
    emit_map_update()


def _on_position_changed(x, y, heading):
    """RoomFinch position-callback subscriber. Fires after every motion
    that updates the robot's pose, from whatever thread did the motion.
    Pushes a 'map_update' so App.tsx redraws."""
    with _state_lock:
        gx = max(0, min(GRID_SIZE - 1, int(x)))
        gy = max(0, min(GRID_SIZE - 1, int(y)))
        state['robot'] = {'x': gx, 'y': gy}
        state['path'].append({'x': gx, 'y': gy})
        if len(state['path']) > 500:
            state['path'] = state['path'][-500:]
        state['grid'][gy][gx] = 1
        state['temperature'] = round(finch.getAverageTemperature(), 2)
    emit_map_update()


finch.register_position_callback(_on_position_changed)


# ---------------------------------------------------------------------------
# Auto-nav worker
# ---------------------------------------------------------------------------
# navigateRoom(finch) no longer takes a stop event, so the 'stop' button
# can only halt the in-progress motion via finch.stop() — the nav loop
# will retry on the next iteration. If a hard stop becomes important,
# thread a stop_event through RoomNav.navigateRoom and check it inside
# the while True loop.
_auto_thread = None


def auto_navigation_worker():
    try:
        navigateRoom(finch)
    except Exception as e:
        # Swallow & report so the SocketIO server keeps running even if
        # navigation crashes mid-run. The frontend gets a status update
        # so the user knows something went wrong.
        print(f"[auto-nav] worker raised: {e}")
        socketio.emit('status_update', {'status': f'auto nav error: {e}'})
        return
    socketio.emit('status_update', {'status': 'automatic navigation complete'})


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


@socketio.on('command')
def handle_command(command):
    """Multiplexed command entry — App.tsx emits 'command' with a string."""
    global _auto_thread
    print("Received command:", command)

    # --- auto nav ----------------------------------------------------
    if command == 'start':
        if _auto_thread is None or not _auto_thread.is_alive():
            _auto_thread = socketio.start_background_task(auto_navigation_worker)
            socketio.emit('status_update', {'status': 'automatic navigation started'})
        else:
            socketio.emit('status_update', {'status': 'auto nav already running'})

    elif command == 'stop':
        # Halts current motion only — see auto_navigation_worker note.
        finch.stop()
        socketio.emit('status_update', {'status': 'stop signaled'})

    elif command == 'reset':
        finch.stop()
        reset_state()
        socketio.emit('status_update', {'status': 'state reset'})

    # --- manual mode -------------------------------------------------
    # Routed through ManualController so anchors land in the same CSV
    # used by auto nav. Position pushes happen automatically via the
    # registered callback; no explicit emit needed here.
    elif command == 'up':
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