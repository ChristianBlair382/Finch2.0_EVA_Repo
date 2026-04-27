print("hello world")
"""
PID Controller
Implements a PID Controller for the finch to more accurate control over where it is going

Primitives provided:
- turnTo(targetHeading)          rotates to the absolute compass heading
- driveStraight(distance)         drive forward <distance> cms with head holding (maintains same compass heading)
- holdHeadingStep(target, base)   one step of the head holding drive straight, use if you know what you are doing
"""
import math
import time
from collections import deque
# Finch class is passed in from where this is called, so not imported here

class CompassAverage:
    """A rolling queue of circular means for averaging the last N compass readings

    Uses trig functions to turn angles to unit vectors to prevent errors when readings are at the wrap-around point of 359-0"""
    def __init__(self, finch, size=5):
        self._finch = finch
        self._buffer = deque(maxlen=max(1, size))
 
    def set_size(self, size):
        """Resize the buffer. Existing samples are preserved up to the new capacity (oldest dropped if shrinking)."""
        newSize = max(1, size)
        if newSize == self._buffer.maxlen:
            return
        self._buffer = deque(self._buffer, maxlen=newSize)
 
    def reset(self):
        """Discard all buffered samples. Call when transitioning between behaviors so a stale buffer doesn't bias the next reading."""
        self._buffer.clear()
 
    def read(self):
        """Take one fresh compass reading, push it into the buffer, return the circular mean of the buffer in degrees [0, 360)."""
        raw_deg = self._finch.getCompass()
        self._buffer.append(math.radians(rawDeg))
 
        meanSin = sum(math.sin(a) for a in self._buffer) / len(self._buffer)
        meanCos = sum(math.cos(a) for a in self._buffer) / len(self._buffer)
        meanRad = math.atan2(meanSin, meanCos)
        return math.degrees(meanRad) % 360

class PIDFinchController:
    """
    The Core PID Controller for the finch

    Uses BirdBrain's getCompass, getEncoder("L"/"R"), setMotors(L/R), resetEncoders() and stop()
    Gets Compass Readings from the CompassAverage Class, using a smaller buffer during turns, and a larger when moving straight
    """

    # ===== Requires tuning =====
    # Field are (Kp, Ki, Kd), proportion, integral, derivative
    # Kp is how much motor differential is pushed per degree off course (Faster the further from target)
    # Ki accumulates error when moving to adjust accordingly based on history (Never too large as it can negatively impact accuracy when close to target)
    # Kd is the scale for the rate of change of error, so it eases off the correction when close to target

    # Default gains for Head Holding while driving straight
    DEFAULT_HEADING_GAINS = (1.5, 0.0, 0.4)
    # Default gains for turning
    DEFAULT_TURN_GAINS = (1.8, 0.05, 0.3)
    # Default gains for driving
    DEFAULT_DRIVE_GAINS = (4.0, 0.0, 0.5)

    # ===== Compass Average Sizes =====
    # Smaller turn average size as it is constently turning, so it would accumulate old readings
    TURN_AVERAGE_SIZE = 2
    # Larger for moving straight as it should be barely changing, so this provides a more accurate reading for when it actually veers off course
    HEADING_AVERAGE_SIZE = 5

    # ===== Hardware Information =====
    WHEEL_CIRCUMFERENCE_CM = 16.4 # Roughly 5.2cm diameter for finch 2.0 according to documentation
    MIN_MOTOR_OUTPUT = 4
    LOOP_RATE_HZ = 20 # To match BirdBrain HTTP rate

    def __init__(self, finch,
                headingGains = None,
                turnGains = None,
                driveGains = None,
                compassAverage = None):
        self._finch = finch
        self.headingGains = headingGains or self.DEFAULT_HEADING_GAINS
        self.turnGains    = turnGains    or self.DEFAULT_TURN_GAINS
        self.driveGains   = driveGains   or self.DEFAULT_DRIVE_GAINS

        # Allows passing in a compass average, but defaults to creating a new one.
        self._compass = compassAverage or CompassAverage(finch, size = self.HEADING_AVERAGE_SIZE)

        self._headingState = self._freshState()
        self._turnState    = self._freshState()
        self._driveState   = self._freshState()

    @staticmethod
    def _freshState():
        return {'integral': 0.0, 
                'prevErr': 0.0,
                'lastT': None}

    @staticmethod
    def _resetState(state):
        state['integral'] = 0.0
        state['prevErr'] = 0.0
        state['lastT']   = None

    @staticmethod
    def _shortestAngleDiff(target, current):
        """Signed shortest angle difference (target - current), in (-180, 180] and handles the 359-0 wrap-around"""
        return (target - current + 180) % 360 - 180
    
    def _pidStep(self, error, gains, state, 
                 outputLimits = (-100,100), 
                 integralLimit = 30.0, 
                 deadband = 0.0):
        """One PID iteration, returns the clamped output"""

        if abs(error) < deadband:
            return 0.0
        
        kp,ki,kd = gains
        now = time.monotonic()
        dt = (now - state['lastT']) if state['lastT'] is not None else 0.0
        state[['lastT']] = now

        if dt > 0:
            state['integral'] += error * dt
            state['integral'] = max(-integralLimit, 
                                    min(integralLimit, state['integral']))
            derivative = (error - state['prevErr']) / dt
        else:
            derivative = 0.0
        state['prevErr'] = error

        output = kp * error + ki * state['integral'] + kd * derivative
        low, high = outputLimits
        return max(low, min(high, output))
    
    def _applyMinFloor(self, output):
        """Boost tiny non-zero outputs above the stiction threshold so the wheels actually move when the error is small."""
        if 0 < abs(output) < self.MIN_MOTOR_OUTPUT:
            return math.copysign(self.MIN_MOTOR_OUTPUT, output)
        return output