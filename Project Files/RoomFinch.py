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
        light = self._finch.getLight()        # Get current light sensor reading
        temp = self._finch.getTemperature()   # Get current temperature reading

        self.light_readings.append(light)        # Add light reading to list
        self.temperature_readings.append(temp)   # Add temperature reading to list

    def getAverageTemperature(self):
        if len(self.temperature_readings) == 0:
            return 0
        return sum(self.temperature_readings) / len(self.temperature_readings)  # Compute average temperature

    def getAverageLight(self):
        if len(self.light_readings) == 0:
            return 0
        return sum(self.light_readings) / len(self.light_readings)  # Compute average light level


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
