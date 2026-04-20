from threading import Event

from flask import Flask
from flask_socketio import SocketIO

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins='*')

GRID_SIZE = 20

state = {
    'grid': [[0 for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)],
    'robot': {'x': 0, 'y': 0},
    'path': [{'x': 0, 'y': 0}],
}

running_event = Event()
worker_thread = None


def emit_map_update():
    """Broadcast current room map state to all connected clients."""
    socketio.emit('map_update', state)


def reset_state():
    state['grid'] = [[0 for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
    state['robot'] = {'x': 0, 'y': 0}
    state['path'] = [{'x': 0, 'y': 0}]


def simulation_worker():
    """Simple deterministic simulator so frontend has live map data during development."""
    x, y = 0, 0
    direction = 1

    while running_event.is_set():
        x += direction
        if x >= GRID_SIZE:
            x = GRID_SIZE - 1
            direction = -1
            y = (y + 1) % GRID_SIZE
        elif x < 0:
            x = 0
            direction = 1
            y = (y + 1) % GRID_SIZE

        state['robot'] = {'x': x, 'y': y}
        state['path'].append({'x': x, 'y': y})
        state['grid'][y][x] = 1

        # Keep payload size bounded as simulation runs.
        if len(state['path']) > 500:
            state['path'] = state['path'][-500:]

        emit_map_update()
        socketio.sleep(0.25)

@socketio.on('connect')
def handle_connect():
    print('Client connected')
    emit_map_update()


@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')


@socketio.on('command')
def handle_command(command):
    """Handle frontend commands: start, stop, reset."""
    global worker_thread

    if command == 'start':
        if not running_event.is_set():
            running_event.set()
            worker_thread = socketio.start_background_task(simulation_worker)
        socketio.emit('status_update', {'status': 'running'})
    elif command == 'stop':
        running_event.clear()
        socketio.emit('status_update', {'status': 'stopped'})
    elif command == 'reset':
        running_event.clear()
        reset_state()
        socketio.emit('status_update', {'status': 'reset'})
        emit_map_update()
    else:
        socketio.emit('status_update', {'status': 'unknown_command', 'command': command})

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
