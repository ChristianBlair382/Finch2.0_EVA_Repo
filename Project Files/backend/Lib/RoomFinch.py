from .BirdBrain import Finch as BirdBrainFinch
from .PidController import PIDFinchController
import math
import time
import keyboard
import threading

# Most numbers are dummy numbers, change after testing, measurements are in cm
class RoomFinch:
    #FRONT_WALL_DIST = 20        # threshold for distance sensor for deciding if there is a wall ahead
    #SIDE_CHECK_DIST = 30        # threshold for deciding if there is a wall to the side when turning to check
    MOVE_STEP = 5               # distance per step
    RETURN_TOLERANCE = 15       # distance tolerance for deciding if the finch has returned to origin
    MIN_STEPS_BEFORE_CYCLE = 20 # avoid false origin detection at the start
    ROTATION_SPEED = 40         # Speed for turning (used in non-PID fallback path), adjust for compass reading speed
    SIDE_DIST_CRITICAL_CLOSE = 10     # Distance threshold to consider the wall on the side too close, causing the finch to back up
    SIDE_DIST_CRITICAL_FAR = 30     # Distance threshold to consider the wall on the side too far, causing the finch to go forward

    # PID-mode settings
    PID_TURN_FALLBACK_ANGLE = 3.0  # Angles smaller than this skip PID and use direct motor control
                                   # (avoids the case where the requested turn is below the PID tolerance)

    def __init__(self, device='A', maxLinearSpeed=100, usePID=True):
        """Construct the RoomFinch.

        Parameters
        ----------
        device : str
            BirdBrain device letter ('A', 'B', or 'C').
        maxLinearSpeed : int
            Speed cap for the legacy (non-PID) move calls.
        usePID : bool
            If True, all motion primitives route through the PIDFinchController
            for closed-loop control. If False (or if the PID later misbehaves),
            the original blocking BirdBrain calls are used as a fallback.
            Toggle at runtime via setUsePID().
        """
        self._finch = BirdBrainFinch(device)
        self.maxLinearSpeed = maxLinearSpeed

        # Approximate position tracking (cm). Origin is where the robot starts.
        self.x_position = 0.0
        self.y_position = 0.0

        # Heading direction in degrees. 0 = initial forward direction.
        # Positive = counter-clockwise as left turn adds and right turn subtracts
        self.heading = 0.0

        self.light_readings = []          # Stores all recorded light sensor readings
        self.temperature_readings = []    # Stores all recorded temperature readings
        self.turnScale = 1.0             # Scale factor for turns to account for carpet, updated if calibrating carpet

        self._hw_lock = threading.Lock()  # Lock for hardware access
        self._stop_event = threading.Event()    # Event to signal threads to stop
        self._scanning_event = threading.Event() # Event to signal when scanning is active

        # ===== PID setup =====
        # Internal heading uses CCW-positive convention; compass uses CW-positive.
        # We capture the initial compass reading and convert via:
        #   internal_heading = (initialCompass - currentCompass) % 360
        # This anchors the internal "0 = initial forward" frame to the real-world compass.
        self._usePID = usePID
        if usePID:
            self._pid = PIDFinchController(self._finch)
            self._initialCompass = self._finch.getCompass()
        else:
            self._pid = None
            self._initialCompass = None

    # ------------------------------------------------------------------
    # PID toggle / heading conversion helpers
    # ------------------------------------------------------------------
    def setUsePID(self, usePID):
        """Toggle PID-based motion at runtime. Useful if PID misbehaves and
        you need to fall back to the original blocking calls without
        restarting."""
        if usePID and self._pid is None:
            self._pid = PIDFinchController(self._finch)
            self._initialCompass = self._finch.getCompass()
        self._usePID = usePID

    def _compassToHeading(self, compass):
        """Convert an absolute compass reading (CW-positive, 0-359) to the
        internal heading frame (CCW-positive, 0 = initial forward)."""
        return (self._initialCompass - compass) % 360

    def _headingToCompass(self, heading):
        """Convert an internal heading to its corresponding absolute compass
        target (the compass value the robot should be reading when pointing
        in that internal heading)."""
        return (self._initialCompass - heading) % 360

    def _syncHeadingFromCompass(self):
        """Read the current (averaged) compass and update self.heading.
        Call after any PID-driven turn to keep the internal heading in
        sync with reality."""
        self.heading = self._compassToHeading(self._pid.getAverageHeading())

    # ------------------------------------------------------------------
    # Motion primitives
    # ------------------------------------------------------------------
    def moveForward(self, distance=None):
        """Move forward by distance cms, defaulting to MOVE_STEP if no input.
        Position is updated using actual encoder-measured distance when PID
        is enabled, or commanded distance otherwise."""
        if distance is None:
            distance = self.MOVE_STEP
        self.recordSensors()  # Record sensors before movement to capture conditions leading to movement

        if self._usePID:
            # driveStraight returns actual cm traveled (from encoders).
            # Lock onto current heading so the robot drives a true straight line.
            targetCompass = self._headingToCompass(self.heading)
            actual = self._pid.driveStraight(distance, targetHeading=targetCompass)
            rad = math.radians(self.heading)
            self.x_position += actual * math.cos(rad)
            self.y_position += actual * math.sin(rad)
        else:
            # Original blocking call
            self._finch.setMove('F', distance, self.maxLinearSpeed)
            rad = math.radians(self.heading)
            self.x_position += distance * math.cos(rad)
            self.y_position += distance * math.sin(rad)

    def forwardSteps(self, distance):
        """Main thread function to move forward and continuously update finch location until an obstacle is detected."""
        step_distance = 1  # Move in smaller increments to allow for more frequent updates
        steps = int(distance / step_distance)
        for _ in range(steps):
            if self._stop_event.is_set():  # Check if stop signal is set by scan thread
                break
            self.moveForward(step_distance)
        self._scanning_event.clear()  # Clear scanning event after movement is done

    def threadScan(self, distance_from_wall):
        """Thread function to continuously scan for obstacles and update finch location."""
        while self._scanning_event.is_set():
            front_distance = self.scanObstacle()
            if front_distance < distance_from_wall:
                # If obstacle detected, stop movement and update position based on last move
                self._stop_event.set()  # Signal to stop movement
                self._finch.stop()  # Stop the finch immediately
                return

    def moveForwardUntil(self, distance=None, distance_from_wall=20):
        """Move forward by distance cms, but stops early if an obstacle is detected in range.
        Returns True if stopped by obstacle, False if completed full distance."""
        if distance is None:
            distance = self.MOVE_STEP
        self._stop_event.clear()
        self._scanning_event.set()

        if self._usePID:
            stopped_by_obstacle = self._cruiseWithObstacleCheck(
                max_distance=distance,
                distance_from_wall=distance_from_wall)
            return stopped_by_obstacle

        # Original (non-PID) path
        for i in range(distance):
            self.moveForward(1)
            if self.scanObstacle() < distance_from_wall:
                self.playBeep(40, 1)
                self._stop_event.set()
                self._finch.stop()
                break
        return self._stop_event.is_set()

    def moveForwardUntilWall(self, distance_from_wall=20):
        """Move forward continuously until an obstacle is detected within
        distance_from_wall cm in front."""
        self._stop_event.clear()
        self._scanning_event.set()

        if self._usePID:
            self._cruiseWithObstacleCheck(
                max_distance=None,
                distance_from_wall=distance_from_wall)
            return

        # Original (non-PID) path
        while True:
            self.moveForward(1)
            front_distance = self.scanObstacle()
            if front_distance < distance_from_wall:
                self.playBeep(40, 1)
                self._stop_event.set()
                self._finch.stop()
                break

    def _cruiseWithObstacleCheck(self, max_distance, distance_from_wall):
        """PID-mode continuous forward motion with obstacle and (optional)
        distance limit. Updates x/y from encoders incrementally so position
        is accurate even when interrupted by a wall.

        Returns True if stopped by obstacle, False if stopped by distance.
        """
        self._finch.resetEncoders()
        time.sleep(0.25)
        self._pid.primeForHeadingHold()
        targetCompass = self._headingToCompass(self.heading)

        rad = math.radians(self.heading)
        last_traveled = 0.0
        period = 1.0 / self._pid.LOOP_RATE_HZ
        stopped_by_obstacle = False

        while True:
            # --- update position incrementally from encoders ---
            leftRot  = self._finch.getEncoder('L')
            rightRot = self._finch.getEncoder('R')
            traveled = ((abs(leftRot) + abs(rightRot)) / 2.0
                        * self._pid.WHEEL_CIRCUMFERENCE_CM)
            delta = traveled - last_traveled
            if delta > 0:
                self.x_position += delta * math.cos(rad)
                self.y_position += delta * math.sin(rad)
                last_traveled = traveled

            # --- distance limit check ---
            if max_distance is not None and traveled >= max_distance:
                self._finch.stop()
                break

            # --- obstacle check ---
            if self.scanObstacle() < distance_from_wall:
                self.playBeep(40, 1)
                self._finch.stop()
                self._stop_event.set()
                stopped_by_obstacle = True
                break

            if self._stop_event.is_set():
                self._finch.stop()
                stopped_by_obstacle = True
                break

            # --- one PID heading-hold tick ---
            self._pid.holdHeadingStep(targetCompass)
            time.sleep(period)

        self._scanning_event.clear()
        return stopped_by_obstacle

    def moveBackward(self, distance=None):
        """Move backward by distance cms, defaulting to MOVE_STEP if no input."""
        if distance is None:
            distance = self.MOVE_STEP

        if self._usePID:
            # Reverse driveStraight: pass negative distance; heading-hold still applies.
            targetCompass = self._headingToCompass(self.heading)
            actual = self._pid.driveStraight(-distance, targetHeading=targetCompass)
            rad = math.radians(self.heading)
            # actual is signed: negative means moved backward
            self.x_position += actual * math.cos(rad)
            self.y_position += actual * math.sin(rad)
        else:
            self._finch.setMove('B', distance, self.maxLinearSpeed)
            rad = math.radians(self.heading)
            self.x_position -= distance * math.cos(rad)
            self.y_position -= distance * math.sin(rad)

    def turnLeft(self, angle=90):
        """Turn left and update heading. Internal heading += angle."""
        # Tiny turns: skip PID (would be below tolerance and produce no motion)
        if self._usePID and angle >= self.PID_TURN_FALLBACK_ANGLE:
            currentCompass = self._pid.getAverageHeading()
            targetCompass = (currentCompass - angle) % 360
            self._pid.turnTo(targetCompass)
            self._syncHeadingFromCompass()
        else:
            self._finch.setTurn('L', angle * self.turnScale, self.ROTATION_SPEED)
            self.heading = (self.heading + angle) % 360


    def turnRight(self, angle=90):
        """Turn right and update heading. Internal heading -= angle."""
        if self._usePID and angle >= self.PID_TURN_FALLBACK_ANGLE:
            currentCompass = self._pid.getAverageHeading()
            targetCompass = (currentCompass + angle) % 360
            self._pid.turnTo(targetCompass)
            self._syncHeadingFromCompass()
        else:
            self._finch.setTurn('R', angle * self.turnScale, self.ROTATION_SPEED)
            self.heading = (self.heading - angle) % 360
            
    def turnToHeading(self, target_heading_internal):
        """PID-only convenience: turn to an absolute internal heading
        (e.g. one of the four cardinal directions captured at start of nav).
        Falls back to relative turning if PID disabled."""
        if self._usePID:
            targetCompass = self._headingToCompass(target_heading_internal)
            self._pid.turnTo(targetCompass)
            self._syncHeadingFromCompass()
        else:
            # Compute shortest relative turn and dispatch
            diff = (target_heading_internal - self.heading + 180) % 360 - 180
            if diff > 0:
                self.turnLeft(diff)
            elif diff < 0:
                self.turnRight(-diff)

    def scanObstacle(self):
        """Returns front distance sensor reading in cm."""
        return self._finch.getDistance()

    def checkRight(self):
        """Turns 90 degrees right to check if there is an obstacle there, then turns back. Used for hugging right wall"""
        self.turnRight(90)
        dist = self._finch.getDistance()
        wall_position = self.returnWallPosition(dist) # Get position of wall on the right for mapping purposes
        if dist < self.SIDE_DIST_CRITICAL_CLOSE:
            # If wall is too close on the right, back up a bit
            print(f"Wall too close on the right at {self.getPosition()}, backing up")
            self.moveBackward(10)
        elif dist > self.SIDE_DIST_CRITICAL_FAR:
            # If wall is too far on the right, go forward a bit to try to find it
            print(f"Wall too far on the right at {self.getPosition()}, moving forward to find wall")
            self.moveForward(10)
        
        self.turnLeft(90)
        return dist, wall_position

    def recordSensors(self):
        """Records the current light and temperature sensor readings and stores them in the respective lists."""
        left_light = self._finch.getLight("left") # Left light sensor (0–100)
        right_light = self._finch.getLight("right") # Right light sensor (0–100)

        avg_light = (left_light + right_light) / 2 # Average the two sensors

        temp = self._finch.getTemperature() # Temperature in °C

        self.light_readings.append(avg_light) # Store averaged light
        self.temperature_readings.append(temp) # Store temperature

    def getAverageTemperature(self):
        if len(self.temperature_readings) == 0:
            return 0
        return sum(self.temperature_readings) / len(self.temperature_readings)  # Compute average temperature

    def getAverageLight(self):
        if len(self.light_readings) == 0:
            return 0
        return sum(self.light_readings) / len(self.light_readings)  # Compute average light level

    def playBeep(self, note=60, duration=1):
        """Plays a beep sound with the given note and duration."""
        self._finch.playNote(note, duration)  # Plays note number (0–100) for duration in seconds up to 16

    def playSuccessSound(self):
        """Plays a success melody."""
        self._finch.playNote(60, 200)  # C note (Middle)
        self._finch.playNote(70, 200)  # E note (Higher)
        self._finch.playNote(80, 300)  # G note (Highest)

    def setBeakColor(self, r, g, b):
        """Sets the color of the Finch's beak LED."""
        self._finch.setBeak(r, g, b)  # Sets RGB beak LED color (0–255 for each color)

    def clearBeak(self):
        """Turns off the beak LED."""
        self._finch.setBeak(0, 0, 0)  # Turns off beak LED

    def displaySymbol(self, symbol_matrix):
        """Displays a symbol on the Finch's 5x5 LED matrix. Input is a 2D list of 0s and 1s."""
        self._finch.setDisplay(symbol_matrix)  # Displays a 5x5 LED pattern on micro:bit

    def clearDisplay(self):
        """Turns off all LEDs on the Finch's 5x5 display."""
        self._finch.setDisplay([[0]*5 for _ in range(5)])  # Turns off all LEDs on 5x5 display
    
    def distanceFromOrigin(self):
        """Distance from (0, 0)."""
        return math.sqrt(self.x_position ** 2 + self.y_position ** 2)

    def hasReturnedToOrigin(self, step_count):
        """Returns true if finch is within RETURN_TOLERANCE range AND out of MIN_STEPS_BEFORE_CYCLE"""
        if step_count < self.MIN_STEPS_BEFORE_CYCLE:
            return False
        return self.distanceFromOrigin() < self.RETURN_TOLERANCE

    def getPosition(self):
        """Return current (x, y, heading), rounded to 1 decimal place"""
        return (round(self.x_position, 1),
                round(self.y_position, 1),
                round(self.heading, 1))

    def calibrateFloor(self):
        """Turns until it detects the same distance in front as initial reading, and sets turnScale accordingly."""
        # Deprecated in favor of compass-based turning.
        initial_distance = self.scanObstacle()
        check_distance = 0
        turn_num = 0
        start_tolerance  = 10  # Prevents early trigger of calibration
        max_turns = 100
        while (check_distance != initial_distance) or (turn_num < start_tolerance):
            self.turnLeft(10)
            check_distance = self.scanObstacle()
            turn_num += 1
            if turn_num >= max_turns:
                print("Calibration failed: couldn't find matching distance after 100 turns, turn scale unchanged.")
                return
        self.turnScale = turn_num / 36
        print(f"Calibration complete. turnScale set to {self.turnScale}")
        
    def manualOverride(self):
        """Manual control of the Finch using letters. Q to quit manual mode."""
        print("\n--- MANUAL OVERRIDE MODE ---")
        print("W = Forward | S = Backward | A = Turn Left | D = Turn Right | Q = Exit\n")

        while True:
            key = keyboard.read_key()
            if key == "a":
                self.turnLeft(1)
            elif key == "d":
                self.turnRight(1)
            elif key == "w":
                self.moveForward(1)
            elif key == "s":
                self.moveBackward(1)
            elif key == "q":
                print("\nExiting manual override mode.\n")
                self.stop()
                break

    def returnWallPosition(self, distance):
        """Returns the (x, y) position of a wall in front of the finch based on current position and heading.
        Returns Float values rounded to 1 decimal place."""
        rad = math.radians(self.heading)
        wall_x = self.x_position + distance * math.cos(rad)
        wall_y = self.y_position + distance * math.sin(rad)
        return (round(wall_x, 1), round(wall_y, 1))
    
    def setTurnScale(self, scale):
        """Sets the turn scale factor, used for calibrating turns on different floor surfaces."""
        self.turnScale = scale

    def stop(self):
        self._finch.stop()

    def stopAll(self):
        self._finch.stopAll()