from RoomFinch import RoomFinch
from room_map import Room_Map
import keyboard
import threading

def searchForCorner(finch: RoomFinch):
    """Searches for the corner of the wall when the wall is lost on the right,
    by turning and taking regular distance scans and records the closest points to the finch"""
    closest_points = []
    for _ in range(6):
        dist = finch._finch.getDistance()
        closest_points.append(dist)
        finch.turnRight(15)
    finch.turnLeft(90)
    closest_points.sort()  # Sort by distance
    return finch.returnWallPosition(closest_points[0]), finch.returnWallPosition(closest_points[1])  # Return position of closest point

overrideFlag = False
#
#def checkForOverride():
#    """Checks for user input to override navigation and enter manual mode"""
#    global overrideFlag
#    keyboard.wait("m")  # Wait until "m" is pressed
#    print("Manual override activated, entering manual mode")
#    overrideFlag = True

# TODO: Finch sensor readings need to be recorded
def navigateRoom(finch: RoomFinch):
    """Navigates the room, minimizing turns"""
    SIDE_WALL_DIST = 150  # Distance threshold to consider the side an outside corner
    BIG_STEP = 60
    RETURN_THRESHOLD = 20  # Distance threshold to consider as returning to start
    STEP_THRESHOLD = 6    # Minimum steps before allowing return to start condition
    steps = 0
    global overrideFlag
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
            #TODO: Forward wall position recording
            print(f"Obstacle detected ahead at {finch.getPosition()}, turning left")
            finch.turnLeft(90)
            continue

        if finch.checkRight() > SIDE_WALL_DIST:
            #No wall on the right, so turn to search to find corner position
            finch.playBeep(80, 1)  # Higher beep for outward corner
            print(f"Wall lost on the right at {finch.getPosition()}, finding wall positions")
            p1, p2 = searchForCorner(finch)
            #TODO: Calculate Coordinates
    if  overrideFlag:
        finch.manualOverride()
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
        
    

    