from BirdBrain import Finch as BirdBrainFinch
import math
import keyboard
import threading

# Most numbers are dummy numbers, change after testing, measurements are in cm
class RoomFinch:
    FRONT_WALL_DIST = 15        # threshold for distance sensor for deciding if there is a wall ahead
    SIDE_CHECK_DIST = 30        # threshold for deciding if there is a wall to the side when turning to check
    MOVE_STEP = 5               # distance per step
    RETURN_TOLERANCE = 15       # distance tolerance for deciding if the finch has returned to origin
    MIN_STEPS_BEFORE_CYCLE = 20 # avoid false origin detection at the start

    def __init__(self, device='A', maxLinearSpeed=100, maxRotationSpeed=75):
        self._finch = BirdBrainFinch(device)
        self.maxLinearSpeed = maxLinearSpeed
        self.maxRotationSpeed = maxRotationSpeed

        # Approximate position tracking (cm). Origin is where the robot starts.
        self.x_position = 0.0
        self.y_position = 0.0

        # Heading direction in degrees. 0 = initial forward direction.
        # Positive = counter-clockwise as left turn adds and right turn subtracts
        self.heading = 0.0

        self.light_readings = []          # Stores all recorded light sensor readings
        self.temperature_readings = []    # Stores all recorded temperature readings
        self.turn_scale = 1.0             # Scale factor for turns to account for carpet, updated if calibrating carpet

        self._hw_lock = threading.Lock()  # Lock for hardware access
        self._stop_event = threading.Event()    # Event to signal threads to stop
        self._scanning_event = threading.Event() # Event to signal when scanning is active

    def moveForward(self, distance=None):
        """Move forward by distance cms, defaulting to MOVE_STEP if no input, at maxLinearSpeed. 
        Then updates approximate coordinate"""
        if distance is None:
            distance = self.MOVE_STEP

        with self._hw_lock:  # Ensure that hardware access is thread-safe
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
                with self._hw_lock:
                    self._finch.stop()  # Stop the finch immediately
                return

    def moveForwardUntil(self, distance=None, distance_from_wall=20):
        """Move forward by distance cms, but stops early if an obstacle is detected in range"""
        if distance is None:
            distance = self.MOVE_STEP
        self._stop_event.clear()  # Clear any previous stop signal
        self._scanning_event.set()  # Signal that scanning should be active

        scan_thread = threading.Thread(target=self.threadScan, args=(distance_from_wall,))
        step_thread = threading.Thread(target=self.forwardSteps, args=(distance,))
        scan_thread.start()
        step_thread.start()
        scan_thread.join()
        step_thread.join()
        return self._stop_event.is_set()  # Returns true if stopped by obstacle, false if stopped by distance traveled

    def moveForwardUntilWall(self, distance_from_wall=20):
        """Move forward until an obstacle is detected within distance_from_wall cm in front. Then updates approximate coordinate"""
        self._stop_event.clear()
        self._scanning_event.set()
        scan_thread = threading.Thread(target=self.threadScan, args=(distance_from_wall,))
        scan_thread.start()
        while self._scanning_event.is_set():
            self.moveForward(1)  # Move in increments to allow for scanning
        self._scanning_event.clear()
        scan_thread.join()


    def moveBackward(self, distance=None):
        """Move backward by distance cms, defaulting to MOVE_STEP if no input, at maxLinearSpeed. 
        Then updates approximate coordinate"""
        if distance is None:
            distance = self.MOVE_STEP

        self._finch.setMove('B', distance, self.maxLinearSpeed)

        rad = math.radians(self.heading)
        self.x_position -= distance * math.cos(rad)
        self.y_position -= distance * math.sin(rad)

    def turnLeft(self, angle=90):
        """Turn left and update heading."""
        self._finch.setTurn('L', angle * self.turn_scale, self.maxRotationSpeed)
        self.heading = (self.heading + angle) % 360

    def turnRight(self, angle=90):
        """Turn right and update heading."""
        self._finch.setTurn('R', angle * self.turn_scale, self.maxRotationSpeed)
        self.heading = (self.heading - angle) % 360

    def scanObstacle(self):
        """Returns front distance sensor reading in cm."""
        with self._hw_lock:  # Ensure that hardware access is thread-safe
            return self._finch.getDistance()

    def checkRight(self):
        """Turns 90 degrees right to check if there is an obstacle there, then turns back. Used for hugging right wall"""
        self.turnRight(90)
        dist = self._finch.getDistance()
        #TODO: Forward wall position recording if dist < threshold
        self.turnLeft(90)
        return dist

    def checkLeft(self):
        """Turns 90 degrees left to check if there is an obstacle there, then turns back."""
        self.turnLeft(90)
        dist = self._finch.getDistance()
        self.turnRight(90)
        return dist

    def recordSensors(self):
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

    def playBeep(self, note=60, duration=100):
        self._finch.playNote(note, duration)  # Plays note number (0–100) for duration in ms

    def playSuccessSound(self):
        self._finch.playNote(60, 200)  # C note (Middle)
        self._finch.playNote(70, 200)  # E note (Higher)
        self._finch.playNote(80, 300)  # G note (Highest)

    def setBeakColor(self, r, g, b):
        self._finch.setBeak(r, g, b)  # Sets RGB beak LED color (0–255 for each color)

    def clearBeak(self):
        self._finch.setBeak(0, 0, 0)  # Turns off beak LED

    def displaySymbol(self, symbol_matrix):
        self._finch.setDisplay(symbol_matrix)  # Displays a 5x5 LED pattern on micro:bit

    def clearDisplay(self):
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
        """Turns until it detects the same distance in front as initial reading, and sets turn_scale accordingly."""
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
        self.turn_scale = turn_num / 36
        print(f"Calibration complete. turn_scale set to {self.turn_scale}")
        
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

    def stop(self):
        self._finch.stop()

    def stopAll(self):
        self._finch.stopAll()
