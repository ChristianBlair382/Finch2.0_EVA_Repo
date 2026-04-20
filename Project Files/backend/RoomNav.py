from Lib.RoomFinch import RoomFinch
from Lib.RoomMap import Room_Map
import keyboard
import threading
import csv
import time

def searchForCorner(finch: RoomFinch):
    """Searches for the corner of the wall when the wall is lost on the right,
    by turning and taking regular distance scans and records the closest points to the finch"""
    closest_points = {}
    for _ in range(6):
        dist = finch.scanObstacle()
        closest_points[dist] = finch.returnWallPosition(dist)
        finch.turnRight(15)
    finch.turnLeft(90)
    closest_points = dict(sorted(closest_points.items()))
    closest_walls = list(closest_points.values())[:2]
    return closest_walls[0], closest_walls[1]

def manualOverride(finch: RoomFinch):
    """Manual control using step-based movement for more consistent coordinate updates."""
    print("\n--- MANUAL OVERRIDE MODE ---")
    print("W = Forward | S = Backward | A = Turn Left | D = Turn Right | SPACE = Set Anchor | Q = Exit\n")

    keyboard.block_key('w')
    keyboard.block_key('a')
    keyboard.block_key('s')
    keyboard.block_key('d')
    keyboard.block_key('space')
    keyboard.block_key('q')

    room_map_manager = Room_Map(finch)
    with open('anchors.csv', 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['x', 'y'])

    space_was_pressed = False

    while True:
        if keyboard.is_pressed('a'):
            finch.turnLeft(90)
        elif keyboard.is_pressed('d'):
            finch.turnRight(90) # Tuned to 100 degrees to account for error in turning and to better align with walls when manually navigating
        elif keyboard.is_pressed('w'):
            finch.moveForward(10)
        elif keyboard.is_pressed('s'):
            finch.moveBackward(10)
        elif keyboard.is_pressed('q'):
            print("\nExiting manual override mode.\n")
            for i in range(0, 3):
                finch.playBeep(70, 1)  # Beep to indicate exiting manual mode
                finch.setBeakColor(0, 128, 0)  # Set beak LED to green to indicate manual mode exit
                time.sleep(0.5)
                finch.setBeakColor(0, 0, 0)  # Set beak LED back to blue (default)
            finch.stop()
            break

        space_pressed = keyboard.is_pressed('space')
        if space_pressed and not space_was_pressed:
            x, y, _ = finch.getPosition()
            room_map_manager.add_anchor_at_position((x, y))
            print(f"Anchor added at {(x, y)}")
        space_was_pressed = space_pressed

        time.sleep(0.02)
#overrideFlag = False
#This will be replaced by frontend socketio in the future
#def checkForOverride():
#    """Checks for user input to override navigation and enter manual mode"""
#    global overrideFlag
#    keyboard.wait("m")  # Wait until "m" is pressed
#    print("Manual override activated, entering manual mode")
#    overrideFlag = True

def navigateRoom(finch: RoomFinch):
    """Navigates the room, minimizing turns"""
    RoomMapManager = Room_Map(finch)
    with open('anchors.csv', 'w', newline='') as csvfile: # Clear the anchors csv file at the start of navigation
        writer = csv.writer(csvfile)
        writer.writerow(['x', 'y'])  # Write header for clarity
    SIDE_WALL_DIST = 150  # Distance threshold to consider the side an outside corner
    BIG_STEP = 60
    RETURN_THRESHOLD = 20  # Distance threshold to consider as returning to start
    STEP_THRESHOLD = 6    # Minimum steps before allowing return to start condition
    steps = 0
    overrideFlag = False
    finch.setBeakColor(0, 0, 255)  # Set beak LED to blue (starting state)
    # Finch approaches first wall
    print("Approaching first wall...")
    finch.playBeep(60, 1)  # Play beep to indicate start
    finch.moveForwardUntilWall()
    # Turn left so the wall is to the right
    finch.turnLeft(90)
    print("Starting navigation")
    finch.setBeakColor(255, 255, 0)  # Change beak LED to yellow (actively mapping)
    #Record starting position
    start = finch.getPosition()
    #overrideThread = threading.Thread(target=checkForOverride)
    #overrideThread.daemon = True  # Daemonize thread to exit when main program exits
    #overrideThread.start()
    while not overrideFlag:
        steps += 1
        pos = finch.getPosition()
        # Check with the threshold to account for error in estimation for if the finch has returned to starting position
        if pos[0]>=start[0]-RETURN_THRESHOLD and pos[0]<=start[0]+RETURN_THRESHOLD and pos[1]>=start[1]-RETURN_THRESHOLD and pos[1]<=start[1]+RETURN_THRESHOLD and steps > STEP_THRESHOLD:
            print(f"Returned to start at {pos}, stopping navigation")
            break

        if finch.moveForwardUntil(BIG_STEP):
            #Stopped by obstacle, so turn left and try again
            RoomMapManager.add_anchor()
            print(f"Obstacle detected ahead at {finch.getPosition()}, turning left")
            finch.turnLeft(90)
            continue

        right_distance, wall_position = finch.checkRight()
        RoomMapManager.add_anchor_at_position(wall_position)  # Add anchor at the current position

        if right_distance > SIDE_WALL_DIST:
            #No wall on the right, so turn to search to find corner position
            finch.playBeep(80, 1)  # Higher beep for outward corner
            print(f"Wall lost on the right at {finch.getPosition()}, finding wall positions")
            p1, p2 = searchForCorner(finch)
            RoomMapManager.add_anchor_at_position(p1)
            RoomMapManager.add_anchor_at_position(p2)

    if overrideFlag:
        manualOverride(finch)
    finch.setBeakColor(0, 255, 0)  # Green beak LED to indicate completion
    finch.playSuccessSound()  # Play success melody

    smile = [
        [0, 1, 0, 1, 0],
        [0, 1, 0, 1, 0],
        [0, 0, 0, 0, 0],
        [1, 0, 0, 0, 1],
        [0, 1, 1, 1, 0]
    ]
        
    finch.displaySymbol(smile)  # Display smile face on 5x5 LED matrix
    print("\nRoom Data Summary")
    print(f"Average Temperature: {round(finch.getAverageTemperature(), 2)} °C")  # Display average temperature
    print(f"Average Light Level: {round(finch.getAverageLight(), 2)}")           # Display average light level