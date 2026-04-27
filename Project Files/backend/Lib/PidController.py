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
    """A rolling queue of readings used to compute the circular means for the last N compass readings

    Uses trig functions to turn angles to unit vectors to prevent errors when readings are at the wrap-around point of 359-0"""
    def __init__(self, finch, size=5):
        self._finch = finch
        self._buffer = deque(maxlen=max(1, size))
 
    def setSize(self, size):
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
        rawDeg = self._finch.getCompass()
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
    # Fields are (Kp, Ki, Kd), proportion, integral, derivative
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
    # Smaller turn average size as it is constantly turning, so it would accumulate old readings
    TURN_AVERAGE_SIZE = 2
    # Larger for moving straight as it should be barely changing, so this provides a more accurate reading for when it actually veers off course
    HEADING_AVERAGE_SIZE = 5

    # ===== Hardware Information =====
    WHEEL_CIRCUMFERENCE_CM = 16.4 # Roughly 5.2cm diameter for finch 2.0 according to documentation
    MIN_MOTOR_OUTPUT = 12 # Keep above constiction range, test and use value where the wheels can move from rest, e.g. higher value for carpet
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
        state['lastT'] = now

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
    

    # ===== Motion Primitives =====
    def turnTo(self, targetHeading, tolerance=2.0, timeout=5.0):
        """Rotate in place to an absolute compass heading.
 
        PID output is the symmetric wheel speed: positive = left turn,
        which on the Finch means left wheel back / right wheel forward.
 
        Uses a tight average size to minimize lag while the heading is
        sweeping. Returns True if target reached within tolerance, False on
        timeout.
        """
        self._resetState(self._turnState)
        # Clear any stale samples from a previous behavior so the size
        # fills with fresh readings as the robot starts moving.
        self._compass.reset()
        self._compass.setSize(self.TURN_AVERAGE_SIZE)
 
        period  = 1.0 / self.LOOP_RATE_HZ
        tStart = time.monotonic()
 
        try:
            while True:
                current = self._compass.read()
                error   = self._shortestAngleDiff(targetHeading, current)
 
                if abs(error) <= tolerance:
                    self._finch.stop()
                    return True
                if time.monotonic() - tStart > timeout:
                    self._finch.stop()
                    return False
 
                speed = self._pidStep(error, self.turnGains,
                                       self._turnState,
                                       outputLimits=(-60, 60))
                speed = self._applyMinFloor(speed)
                # +error means CCW: left wheel reverses, right wheel forward
                self._finch.setMotors(-speed, speed)
                time.sleep(period)
        finally:
            # Restore the looser size for any subsequent heading-hold work.
            self._compass.setSize(self.HEADING_AVERAGE_SIZE)
    
    def driveStraight(self, distanceCm, baseSpeed=40, targetHeading=None):
        """Drive forward <distanceCm> while holding heading via PID.
 
        Two PID loops run together:
          - Distance loop: encoder feedback -> base forward speed
          - Heading loop:  averaged compass -> motor differential
 
        If targetHeading is None, locks onto whatever the compass reads
        (averaged) at the moment driveStraight is called.
 
        Returns actual distance traveled in cm.
        """
        self._finch.resetEncoders()
        time.sleep(0.25)    # encoders need time to zero
        self._resetState(self._headingState)
        self._resetState(self._driveState)
 
        # Use the larger average size for cruise: heading is near-constant
        self._compass.reset()
        self._compass.setSize(self.HEADING_AVERAGE_SIZE)
        # Prime the average with a few samples so the first read isn't a single noisy measurement.
        for _ in range(self.HEADING_AVERAGE_SIZE):
            self._compass.read()
            time.sleep(0.01)
 
        if targetHeading is None:
            targetHeading = self._compass.read()
 
        period      = 1.0 / self.LOOP_RATE_HZ
        forward     = math.copysign(1, distanceCm)
        targetDist = abs(distanceCm)
 
        while True:
            # distance feedback (average both encoders, in cm)
            leftRot  = self._finch.getEncoder('L')
            rightRot = self._finch.getEncoder('R')
            traveled  = ((abs(leftRot) + abs(rightRot)) / 2.0
                         * self.WHEEL_CIRCUMFERENCE_CM)
            distErr  = targetDist - traveled
 
            if distErr <= 0.5:                  # within 5 mm
                self._finch.stop()
                return traveled
 
            # Distance PID -> commanded forward base speed (0..baseSpeed)
            base = self._pidStep(distErr, self.driveGains,
                                  self._driveState,
                                  outputLimits=(0, baseSpeed))
 
            # Heading PID -> differential to add/subtract from each wheel
            headingErr = self._shortestAngleDiff(targetHeading,
                                                    self._compass.read())
            diff = self._pidStep(headingErr, self.headingGains,
                                  self._headingState,
                                  outputLimits=(-30, 30),
                                  deadband=0.5)
 
            # Combine: forward base +- differential, then clamp
            left  = forward * base - diff
            right = forward * base + diff
            left  = max(-100, min(100, left))
            right = max(-100, min(100, right))
            self._finch.setMotors(left, right)
            time.sleep(period)

    def holdHeadingStep(self, targetHeading, baseSpeed=40):
        """Run ONE heading-hold update and return immediately.
 
        Call this repeatedly from an outer loop (e.g. wall following or
        the web app navigation tick) when you want continuous forward
        motion with PID-corrected heading but want to keep control of
        the loop yourself.
 
        This assumes the compass average is already in HEADING_AVERAGE_SIZE
        mode and has been primed. If you're calling this after a
        turnTo(), call primeForHeadingHold() once first.
        """
        headingErr = self._shortestAngleDiff(targetHeading,
                                                self._compass.read())
        diff = self._pidStep(headingErr, self.headingGains,
                              self._headingState,
                              outputLimits=(-30, 30),
                              deadband=0.5)
        left  = baseSpeed - diff
        right = baseSpeed + diff
        self._finch.setMotors(max(-100, min(100, left)),
                              max(-100, min(100, right)))
 
    def primeForHeadingHold(self):
        """Call once before starting a holdHeadingStep loop. Resizes the
        compass average size for cruise mode, clears stale samples, and
        fills the buffer so the first holdHeadingStep call gets a fully
        averaged reading instead of a single noisy one."""
        self._resetState(self._headingState)
        self._compass.reset()
        self._compass.setSize(self.HEADING_AVERAGE_SIZE)
        for _ in range(self.HEADING_AVERAGE_SIZE):
            self._compass.read()
            time.sleep(0.01)
 
    def getAverageHeading(self):
        """Convenience: read the current filtered heading without driving
        the motors. Useful for RoomFinch to capture an absolute target
        before starting a behavior, or to update its internal heading
        attribute after a turn completes."""
        return self._compass.read()
 
    def resetAll(self):
        """Reset every internal PID loop and the compass average. Call when
        transitioning between behaviors so stale state doesn't leak
        across modes."""
        self._resetState(self._headingState)
        self._resetState(self._turnState)
        self._resetState(self._driveState)
        self._compass.reset()