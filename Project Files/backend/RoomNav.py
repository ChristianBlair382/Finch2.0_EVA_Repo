from Lib.RoomFinch import RoomFinch
from Lib.RoomMap import Room_Map
import keyboard
import threading
import csv
import time

# RoomNav uses RoomFinch's public interface, which transparently switches
# between PID-based and direct motor control based on how RoomFinch was
# constructed (usePID flag). This file does NOT need to know which mode
# is active. The notes below describe behavior assuming PID is on.

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
    """Manual control using step-based movement for more consistent coordinate updates.

    Note: PID-based turns have a tolerance of ~2 degrees, so requesting
    sub-tolerance turns (e.g. turnLeft(1)) automatically falls back to
    direct motor control inside RoomFinch. The bigger 90-degree turns
    below go through PID."""
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
    """Navigates the room using right-wall following.

    Strategy (assuming PID is enabled in RoomFinch):
      - Approach the first wall, then turn left so the wall is on the right.
      - Capture that wall-aligned heading as a 'cardinal' reference. Every
        subsequent turn snaps back to one of the four cardinal headings
        (wall_heading + 0/90/180/270), which prevents rotational drift
        from accumulating across many turns.
      - Drive forward in BIG_STEP-sized cruises with continuous heading-hold,
        watching for inward corners (front sensor trips) and outward corners
        (right side opens up). Drop map anchors at every corner event.
      - Terminate when the robot returns to start position.

    With PID off, this still works but turns drift more, so the cardinal
    snap is less effective.
    """
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
    # Align parallel to the wall now that it's on the right. Corrects
    # any drift introduced by the moveForwardUntilWall + turn sequence
    # before we lock in cardinals.
    finch.alignParallelToRightWall()
    print("Starting navigation")
    finch.setBeakColor(255, 255, 0)  # Change beak LED to yellow (actively mapping)

    # Capture the four cardinal headings derived from the wall-aligned start.
    # Used to snap turns back to canonical directions instead of drifting.
    wall_heading = finch.heading
    cardinals = [(wall_heading + offset) % 360 for offset in (0, 90, 180, 270)]
    cardinal_idx = 0  # current index into cardinals[]
    print(f"Wall-aligned heading captured: {wall_heading:.1f}. "
          f"Cardinals: {[round(c, 1) for c in cardinals]}")

    #Record starting position
    start = finch.getPosition()
    while not overrideFlag:
        steps += 1
        pos = finch.getPosition()
        # Check with the threshold to account for error in estimation for if the finch has returned to starting position
        if pos[0]>=start[0]-RETURN_THRESHOLD and pos[0]<=start[0]+RETURN_THRESHOLD and pos[1]>=start[1]-RETURN_THRESHOLD and pos[1]<=start[1]+RETURN_THRESHOLD and steps > STEP_THRESHOLD:
            print(f"Returned to start at {pos}, stopping navigation")
            break

        if finch.moveForwardUntil(BIG_STEP):
            # Stopped by obstacle: inward corner. Turn left to next cardinal CCW.
            RoomMapManager.add_anchor()
            print(f"Obstacle detected ahead at {finch.getPosition()}, turning left to next cardinal")
            cardinal_idx = (cardinal_idx + 1) % 4
            print(f"[nav] inward corner. cardinal_idx -> {cardinal_idx}, "f"target={cardinals[cardinal_idx]:.1f}")
            finch.turnToHeading(cardinals[cardinal_idx])
            # Re-align: turning into the new wall direction may leave us
            # slightly off-parallel, and clipping into the wall is more
            # likely on the new heading than during a long straightaway.
            finch.alignParallelToRightWall()
            print(f"[nav] post-turn position: {finch.getPosition()}")
            continue

        right_distance, wall_position = finch.checkRight()
        RoomMapManager.add_anchor_at_position(wall_position)  # Add anchor at the current position

        if right_distance > SIDE_WALL_DIST:
            # No wall on the right: outward corner. Search for the new wall positions
            # for mapping, then turn right to the next cardinal CW to follow it.
            finch.playBeep(80, 1)  # Higher beep for outward corner
            print(f"Wall lost on the right at {finch.getPosition()}, finding wall positions")
            p1, p2 = searchForCorner(finch)
            RoomMapManager.add_anchor_at_position(p1)
            RoomMapManager.add_anchor_at_position(p2)
            cardinal_idx = (cardinal_idx - 1) % 4
            finch.turnToHeading(cardinals[cardinal_idx])
            # Re-align to the new wall on the right after rounding the corner.
            finch.alignParallelToRightWall()

    if overrideFlag:
        manualOverride(finch)
    finch.stopTail()                  # Tail off — navigation complete
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