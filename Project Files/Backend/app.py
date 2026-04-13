from flask import Flask
from flask_socketio import SocketIO
from RoomFinch import RoomFinch
from RoomNav import navigateRoom
import threading
import time

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

robot = None
running = False

@socketio.on('connect')
def handle_connect():
    print('Client connected')

#START ROBOT FROM REACT
@socketio.on('start')
def start_robot():
    global robot, running

    if running:
        return

    print("Starting robot...")
    running = True
    robot = RoomFinch()

    thread = threading.Thread(target=run_robot)
    thread.start()

#STOP ROBOT
@socketio.on('stop')
def stop_robot():
    global running, robot
    running = False
    if robot:
        robot.stopAll()
    print("Robot stopped")

#MAIN LOOP THAT SENDS DATA
def run_robot():
    global robot, running

    while running:
        #GET POSITION FROM YOUR CODE
        pos = robot.getPosition()

        data = {
            "x": pos[0],
            "y": pos[1],
            "heading": pos[2]
        }

        #SEND TO REACT
        socketio.emit("robot_data", data)

        time.sleep(0.2)  #Adjust speed

    print("Thread ended")

if __name__ == '__main__':
    socketio.run(app, port=5000)