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
        self.scanning = False

    def moveForward(self, distance=None):
        """Move forward by distance cms, defaulting to MOVE_STEP if no input, at maxLinearSpeed. 
        Then updates approximate coordinate"""
        if distance is None:
            distance = self.MOVE_STEP

        self._finch.setMove('F', distance, self.maxLinearSpeed)

        rad = math.radians(self.heading)
        self.x_position += distance * math.cos(rad)
        self.y_position += distance * math.sin(rad)

    def threadForwardSteps(self, distance):
        """Thread function to move forward and continuously update finch location until an obstacle is detected."""
        step_distance = 1  # Move in smaller increments to allow for more frequent updates
        steps = int(distance / step_distance)
        for _ in range(steps):
            self.moveForward(step_distance)
            front_distance = self.scanObstacle()
        self.scanning = False  # Stop scanning thread after movement is complete

    def threadScan(self, distance_from_wall):
        """Thread function to continuously scan for obstacles and update finch location."""
        while True:
            front_distance = self.scanObstacle()
            if front_distance < self.FRONT_WALL_DIST:
                # If obstacle detected, stop movement and update position based on last move
                self.stop()
                self.scanning = False
                # Position is updated in moveForward, so we can just break here
                break
            if not self.scanning:
                break

    def moveForwardUntil(self, distance=None, distance_from_wall=20):
        """Move forward by distance cms, defaulting to MOVE_STEP if no input, at maxLinearSpeed.
        But stops if an obstacle is detected within distance_from_wall cm in front. Then updates approximate coordinate"""
        if distance is None:
            distance = self.MOVE_STEP
        self.scanning = True
        forward_thread  = threading.Thread(target=self.threadForwardSteps, args=(distance,))
        scan_thread = threading.Thread(target=self.threadScan, args=(distance_from_wall,))
        forward_thread.start()
        scan_thread.start()


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
        return self._finch.getDistance()

    def checkRight(self):
        """Turns 90 degrees right to check if there is an obstacle there, then turns back. Used for hugging right wall"""
        self.turnRight(90)
        dist = self._finch.getDistance()
        self.turnLeft(90)
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
        while (check_distance != initial_distance) and (turn_num < 10):
            self.turnLeft(10)
            check_distance = self.scanObstacle()
            turn_num += 1
            if turn_num >= 100:
                print("Calibration failed: couldn't find matching distance after 100 turns, turn scale unchanged.")
                return
        self.turn_scale = turn_num / 36
        print(f"Calibration complete. turn_scale set to {self.turn_scale}")
        
    def manual_override(self):
        """Manual control of the Finch using letters. Q to quit manual mode."""
        print("\n--- MANUAL OVERRIDE MODE ---")
        print("W = Forward | S = Backward | A = Turn Left | D = Turn Right | Q = Exit\n")

        while True:
            print(keyboard.read_key())
            if keyboard.read_key() == "a":
                self.turnLeft(1)
            elif keyboard.read_key() == "d":
                self.turnRight(1)
            elif keyboard.read_key() == "w":
                self.moveForward(1)
            elif keyboard.read_key() == "s":
                self.moveBackward(1)
            elif keyboard.read_key() == "q":
                print("\nExiting manual override mode.\n")
                self.stop()
                break

    def stop(self):
        self._finch.stop()

    def stopAll(self):
        self._finch.stopAll()
