from Lib.RoomFinch import RoomFinch
from Lib.RoomMap import Room_Map
import csv
import time

# RoomNav uses RoomFinch's public interface, which transparently switches
# between PID-based and direct motor control based on how RoomFinch was
# constructed (usePID flag). This file does NOT need to know which mode
# is active. The notes below describe behavior assuming PID is on.

def searchForCorner(finch: RoomFinch):
    """Searches for the corner of the wall when the wall is lost on the right,
    by turning and taking regular distance scans, and returns the two closest
    points to the finch in *traversal order* — i.e. ordered by the scan angle
    they were taken at, not by distance.

    Traversal order matters because anchors get written to anchors.csv
    sequentially as the robot moves around the room; sorting by distance
    here would produce out-of-sequence points whenever the closer wall
    point happens to be at a later scan angle than the farther one."""
    points_in_order = []  # list of (distance, wall_position) in scan order
    for _ in range(6):
        dist = finch.scanObstacle()
        points_in_order.append((dist, finch.returnWallPosition(dist)))
        finch.turnRight(15)
    finch.turnLeft(90)
    # Pick the two closest scans, but return them in the order they were
    # taken so the CSV stays monotonic along the traversal path.
    indexed = list(enumerate(points_in_order))
    closest_two = sorted(indexed, key=lambda iv: iv[1][0])[:2]
    closest_two.sort(key=lambda iv: iv[0])  # back to scan-order
    return closest_two[0][1][1], closest_two[1][1][1]

class ManualController:
    """Stateless command interface for frontend-driven manual control.

    Replaces the old keyboard-poll-loop manualOverride function. Each method
    is a single discrete action triggered by a button press on the frontend
    (over Flask-SocketIO or similar). The controller owns the Room_Map
    instance so anchors land in the same per-session anchors.csv as auto
    nav, but holds no UI state of its own — sequence/timing is the
    frontend's responsibility.

    Typical wiring:
        controller = ManualController(finch)
        @socketio.on('manual_forward')
        def _(): controller.forward()
        @socketio.on('manual_scan')
        def _(): controller.scan_anchor()
        ...
    """

    # Step sizes — the frontend sees only the action, not the magnitude,
    # so these stay tunable here.
    STEP_CM      = 10
    TURN_DEG     = 90

    def __init__(self, finch: RoomFinch):
        self.finch = finch
        self.room_map = Room_Map(finch)
        # Reset anchors.csv at controller construction (same pattern as
        # navigateRoom) — one fresh map per manual session.
        with open('anchors.csv', 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['x', 'y'])
        self.finch.setBeakColor(0, 0, 255)
        print("Manual controller ready. Awaiting commands.")

    # --- motion commands -------------------------------------------------
    def forward(self):
        self.finch.moveForward(self.STEP_CM)

    def backward(self):
        self.finch.moveBackward(self.STEP_CM)

    def left(self):
        self.finch.turnLeft(self.TURN_DEG)

    def right(self):
        self.finch.turnRight(self.TURN_DEG)

    def stop(self):
        """Halt any in-progress motion. Useful as an emergency-stop button."""
        self.finch.stop()

    # --- anchor commands -------------------------------------------------
    def scan_anchor(self):
        """Take a front-distance reading and project it to a wall coordinate,
        then add to the map. This is the wall-projection version (matches
        auto nav) — *not* the robot's own position, ahem ahem. To anchor the robot's
        position instead, use anchor_at_robot_position()."""
        self.room_map.add_anchor()
        last = self.room_map.anchorList[-1] if self.room_map.anchorList else None
        print(f"Wall anchor added at {last}")

    def anchor_at_robot_position(self):
        """Drop an anchor at the robot's current (x, y). Useful for marking
        traversal waypoints rather than walls."""
        x, y, _ = self.finch.getPosition()
        self.room_map.add_anchor_at_position((x, y))
        print(f"Position anchor added at {(x, y)}")

    # --- session lifecycle ----------------------------------------------
    def shutdown(self):
        """Frontend-driven equivalent of the old 'q' key: play exit
        sequence and stop the robot. Safe to call more than once."""
        print("Manual controller shutting down.")
        for _ in range(3):
            self.finch.playBeep(70, 1)
            self.finch.setBeakColor(0, 128, 0)
            time.sleep(0.5)
            self.finch.setBeakColor(0, 0, 0)
        self.finch.stop()


def navigateRoom(finch: RoomFinch, stop_event=None):
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

    stop_event (optional threading.Event) lets a caller request an early
    exit from the main loop. The loop checks it once per iteration, so
    after the caller sets it the navigator finishes whatever motion is in
    flight (or is interrupted by finch.stop()) and breaks out. Without it
    navigateRoom is uninterruptible from outside, which is what the
    Flask-SocketIO 'stop' / manual-override buttons need.
    """
    def _should_stop():
        return stop_event is not None and stop_event.is_set()
    RoomMapManager = Room_Map(finch)
    with open('anchors.csv', 'w', newline='') as csvfile: # Clear the anchors csv file at the start of navigation
        writer = csv.writer(csvfile)
        writer.writerow(['x', 'y'])  # Write header for clarity
    SIDE_WALL_DIST = 150  # Distance threshold to consider the side an outside corner
    BIG_STEP = 40
    RETURN_THRESHOLD = 20  # Distance threshold to consider as returning to start
    STEP_THRESHOLD = 6    # Minimum steps before allowing return to start condition
    steps = 0
    finch.setBeakColor(0, 0, 255)  # Set beak LED to blue (starting state)
    # Finch approaches first wall
    print("Approaching first wall...")
    finch.playBeep(60, 1)  # Play beep to indicate start
    finch.moveForwardUntilWall()
    # Robot is now facing the wall. Skip turnLeft(90) and align directly
    # — the alignment routine already does a CCW 90° + B rotation in
    # assume_facing_wall mode, so the wall ends up on the right and we
    # avoid two wasted turns.
    finch.alignParallelToRightWall(assume_facing_wall=True)
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
    while True:
        # External stop request (e.g. frontend 'stop' button or any manual
        # command coming through ManualController). Checked once per
        # iteration; in-flight motion is interrupted by finch.stop() at the
        # caller, so the worst-case latency is one BIG_STEP cruise.
        if _should_stop():
            print("Auto-nav stop signaled, exiting loop")
            break

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

    finch.stopTail()                  # Tail off — navigation complete

    # Skip the completion fanfare if we were halted externally — a user
    # who pressed 'stop' or grabbed manual control doesn't want a success
    # melody and smile face pretending the room was finished.
    if _should_stop():
        finch.setBeakColor(0, 0, 255)  # Back to idle blue
        print("\nNavigation halted by external stop request.")
        return

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