from threading import Event
from flask import Flask
from flask_socketio import SocketIO
from Lib.RoomFinch import RoomFinch
from RoomNav import navigateRoom, scan_anchor

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins='*')

GRID_SIZE = 20

finch = RoomFinch('A')

state = {
    'grid': [[0 for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)],
    'robot': {'x': 0, 'y': 0},
    'path': [{'x': 0, 'y': 0}],
    'temperature': 0,
    'light': 0
}

running_event = Event()
worker_thread = None

def emit_map_update():
    """Send updated map data to frontend"""
    socketio.emit('map_update', state)


def reset_state():
    """Reset grid and robot tracking"""
    state['grid'] = [[0 for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
    state['robot'] = {'x': 0, 'y': 0}
    state['path'] = [{'x': 0, 'y': 0}]
    state['temperature'] = 0
    state['light'] = 0
    emit_map_update()

def update_position():
    x, y, _ = finch.getPosition()

    # Attach values so frontend grid never breaks
    x = max(0, min(GRID_SIZE - 1, int(x)))
    y = max(0, min(GRID_SIZE - 1, int(y)))

    state['robot'] = {'x': x, 'y': y}
    state['path'].append({'x': x, 'y': y})
    state['temperature'] = round(finch.getAverageTemperature(), 2)
    state['light'] = round(finch.getAverageLight(), 2)
    
    if 0 <= y < GRID_SIZE and 0 <= x < GRID_SIZE:
        state['grid'][y][x] = 1

    if len(state['path']) > 500:
        state['path'] = state['path'][-500:]

    emit_map_update()

def auto_navigation_worker():
    """Runs Finch automatic room navigation
    in the background while giving updates"""
    navigateRoom(finch, running_event)
    update_position()
    socketio.emit(
        'status_update',
        {'status': 'automatic navigation complete'}
    )


@socketio.on('connect')
def handle_connect():
    print("Client connected")
    emit_map_update()

@socketio.on('disconnect')
def handle_disconnect():
    print("Client disconnected")

@socketio.on('command')
def handle_command(command):
    """Receives commands from frontend"""
    global worker_thread
    print("Received command:", command)

    # Automatic Controls
    if command == 'start':
        if not running_event.is_set():
            running_event.set()
            worker_thread = socketio.start_background_task(
                auto_navigation_worker
            )
        
    # Stop Finch
    elif command == 'stop':
        running_event.clear()
        finch.stopAll()

    # Reset frontend map
    elif command == 'reset':
        running_event.clear()
        finch.stopAll()
        reset_state()
        
    # Manual move forward
    elif command == 'up':
        finch.moveForward(10)
        update_position()

    # Manual move backward
    elif command == 'down':
        finch.moveBackward(10)
        update_position()

    # Manual turn left
    elif command == 'left':
        finch.turnLeft(15)
        update_position()

    # Manual turn right
    elif command == 'right':
        finch.turnRight(15)
        update_position()

    # Manual scan anchor button
    elif command == 'scan_anchor':
        scan_anchor(finch)
        update_position()

    else:
        socketio.emit(
            'status_update',
            {'status': 'unknown command'}
        )


if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
