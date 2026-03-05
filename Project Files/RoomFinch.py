from BirdBrain import Finch as BirdBrainFinch
import math

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
        
    def moveForward(self, distance=None):
        """Move forward by distance cms, defaulting to MOVE_STEP if no input, at maxLinearSpeed. 
        Then updates approximate coordinate"""
        if distance is None:
            distance = self.MOVE_STEP

        self._finch.setMove('F', distance, self.maxLinearSpeed)

        rad = math.radians(self.heading)
        self.x_position += distance * math.cos(rad)
        self.y_position += distance * math.sin(rad)

    def turnLeft(self, angle=90):
        """Turn left and update heading."""
        self._finch.setTurn('L', angle, self.maxRotationSpeed)
        self.heading = (self.heading + angle) % 360

    def turnRight(self, angle=90):
        """Turn right and update heading."""
        self._finch.setTurn('R', angle, self.maxRotationSpeed)
        self.heading = (self.heading - angle) % 360

    def scanObstacle(self):
        """Returns front distance sensor reading in cm."""
        return self._finch.getDistance()

    def checkRight(self):
        """Turns 90 degrees right to check if there is an obstacle there, then turns back. Used for hugging right wall"""
        self._finch.setTurn('R', 90, self.maxRotationSpeed)
        dist = self._finch.getDistance()
        self._finch.setTurn('L', 90, self.maxRotationSpeed)
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
        """Return current (x, y, heading). (For Debugging)"""
        return (round(self.x_position, 1),
                round(self.y_position, 1),
                round(self.heading, 1))

    def stop(self):
        self._finch.stop()

    def stopAll(self):
        self._finch.stopAll()
