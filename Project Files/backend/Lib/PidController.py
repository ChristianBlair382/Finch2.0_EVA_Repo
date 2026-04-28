"""
PID Controller
Implements a PID Controller for the finch to give more accurate control
over where it is going.

Primitives provided:
- turnTo(targetHeading)         rotates to the absolute heading
- driveStraight(distanceCm)     drives forward <distanceCm> cm with heading hold
- holdHeadingStep(target, base) one tick of heading-hold drive, use if you
                                want to own the outer loop yourself

All speed/tolerance/gain values are exposed as class constants on
PIDFinchController. Tweak those at the top of the class to change behavior
globally rather than editing function bodies.
"""
import math
import time
from collections import deque
# Finch class is passed in from where this is called, so not imported here.


# =============================================================================
# Heading sources
# =============================================================================
class CompassAverage:
    """A rolling queue of readings used to compute a circular mean over the
    last N compass readings. Uses unit-vector averaging to handle the 359-0
    wrap-around correctly.

    ========== NOT CURRENTLY USED ==========
    The Finch we're testing on has a broken/uncalibrated compass, so we use
    EncoderHeading below instead. Kept here as a drop-in replacement if a
    future Finch has a working compass — pass an instance via the
    compassAverage parameter of PIDFinchController.__init__.
    =======================================
    """
    def __init__(self, finch, size=5, useRawMagnetometer=False):
        self._finch = finch
        self._buffer = deque(maxlen=max(1, size))
        self._useRaw = useRawMagnetometer

    def _readHeading(self):
        if self._useRaw:
            mx = self._finch.getMagnetometer('X')
            my = self._finch.getMagnetometer('Y')
            return math.degrees(math.atan2(my, mx)) % 360
        return self._finch.getCompass()

    def setSize(self, size):
        newSize = max(1, size)
        if newSize == self._buffer.maxlen:
            return
        self._buffer = deque(self._buffer, maxlen=newSize)

    def reset(self):
        self._buffer.clear()

    def read(self):
        rawDeg = self._readHeading()
        self._buffer.append(math.radians(rawDeg))
        meanSin = sum(math.sin(a) for a in self._buffer) / len(self._buffer)
        meanCos = sum(math.cos(a) for a in self._buffer) / len(self._buffer)
        meanRad = math.atan2(meanSin, meanCos)
        return math.degrees(meanRad) % 360


class EncoderHeading:
    """Heading from wheel odometry using signed encoder readings.

    The Finch encoders return signed values (positive = forward, negative
    = backward) so we can compute heading change directly from encoder
    deltas without any motor-command bookkeeping.

    Wheelbase calibration: the wheelbase_cm parameter is calibrated by
    pivoting the robot exactly one full physical rotation and computing
    wheelbase = avg_encoder_rotations * wheel_circumference / pi.
    """

    def __init__(self, finch, wheelbase_cm=10.5, debug=False):
        self._finch = finch
        self.wheelbase_cm = wheelbase_cm
        self.WHEEL_CIRCUMFERENCE_CM = 16.4
        self._heading = 0.0
        self._last_left = 0.0
        self._last_right = 0.0
        self.debug = debug

    def reset(self, initial_heading=0.0):
        """Set heading to a known value and re-baseline encoder readings."""
        self._heading = initial_heading
        self._last_left  = self._finch.getEncoder('L')
        self._last_right = self._finch.getEncoder('R')

    def resyncFromEncoders(self):
        """Re-baseline last-encoder values without changing the heading
        accumulator. Call after resetEncoders() externally so the next
        read() doesn't see the reset as a phantom rotation."""
        self._last_left  = self._finch.getEncoder('L')
        self._last_right = self._finch.getEncoder('R')

    def setSize(self, size):
        pass  # API compatibility with CompassAverage

    def noteMotorCommand(self, left_speed, right_speed):
        """No-op: signed encoders mean we don't need motor-command tracking.
        Kept for API compatibility — _setMotorsTracked still calls it."""
        pass

    def read(self):
        # Signed encoder readings: forward is positive, reverse is negative.
        left  = self._finch.getEncoder('L')
        right = self._finch.getEncoder('R')

        # Wheel travel since last read (signed, in cm)
        d_left  = (left  - self._last_left)  * self.WHEEL_CIRCUMFERENCE_CM
        d_right = (right - self._last_right) * self.WHEEL_CIRCUMFERENCE_CM

        self._last_left  = left
        self._last_right = right

        # Differential drive kinematics. Left pivot (left back, right
        # forward) -> (d_right - d_left) large and positive. The leading
        # minus puts us in CW-positive convention to match the rest of
        # the PID stack (left turn = heading decreases).
        delta_rad = -(d_right - d_left) / self.wheelbase_cm
        delta_deg = math.degrees(delta_rad)

        if self.debug:
            print(f"    [enc] L={left:+.2f} R={right:+.2f}  "
                  f"dL={d_left:+.2f}cm dR={d_right:+.2f}cm  "
                  f"delta_deg={delta_deg:+.2f}  heading={self._heading:.1f}")

        self._heading = (self._heading + delta_deg) % 360
        return self._heading


# =============================================================================
# PID Controller
# =============================================================================
class PIDFinchController:
    """
    Core PID controller for the Finch.

    Uses BirdBrain's getEncoder('L'/'R'), setMotors(L, R), resetEncoders()
    and stop(). Heading source is pluggable via the compassAverage parameter
    — defaults to EncoderHeading for hardware with broken compass.

    All tunable values are class constants below. Most behavior changes
    should be made by editing those constants rather than function bodies.
    """

    # ===== PID gains (Kp, Ki, Kd) =====
    # Heading-hold during forward motion. Kp scales how aggressively we
    # steer to correct heading drift. Small Ki fights consistent bias from
    # uneven motors. Kd damps oscillation.
    DEFAULT_HEADING_GAINS = (0.8, 0.02, 0.4)
    # Turn-in-place. Lower Kp = gentler approach to target = less wobble.
    # Higher Kd = more damping = cleaner stop with no overshoot.
    # Optimal values from tuning: (0.3, 0.0, 0.15)
    DEFAULT_TURN_GAINS    = (0.3, 0.0, 0.15)
    # Distance-ramp for driveStraight. Kp determines how aggressively we
    # cruise at full speed vs ramp down near the target.
    DEFAULT_DRIVE_GAINS   = (4.0, 0.0, 0.5)

    # ===== Speed limits (motor command units, 0-100) =====
    # All these MUST be greater than MIN_MOTOR_OUTPUT or the PID's
    # proportional ramp gets squashed by the stiction floor.
    #
    # Lower these to make the robot move more gently.
    TURN_OUTPUT_LIMIT          = 15  # Max wheel speed during turnTo pivots
    HEADING_OUTPUT_LIMIT       = 12  # Max steering differential during cruise
    DRIVE_HEADING_OUTPUT_LIMIT = 12  # Max steering differential during driveStraight
    DEFAULT_DRIVE_BASE_SPEED   = 35  # Forward speed for driveStraight
    DEFAULT_CRUISE_BASE_SPEED  = 25  # Forward speed for holdHeadingStep cruise

    # ===== Tolerances and deadbands =====
    TURN_TOLERANCE_DEG     = 2.0   # turnTo exits when within this of target
    TURN_TIMEOUT_SEC       = 7.0   # turnTo gives up after this long
    HEADING_DEADBAND_DEG   = 2.0   # heading PID ignores errors smaller than this
    DRIVE_TOLERANCE_CM     = 0.5   # driveStraight exits when within 5mm

    # ===== Heading-source averaging window =====
    # Only meaningful for CompassAverage. EncoderHeading ignores setSize().
    TURN_AVERAGE_SIZE = 2
    HEADING_AVERAGE_SIZE = 3

    # ===== Hardware =====
    WHEEL_CIRCUMFERENCE_CM = 16.4
    # Stiction floor: motor commands below this don't reliably move the
    # wheels from rest. Lower for slick floors, raise for carpet. Setting
    # this too low means the PID stalls before reaching the target;
    # setting it too high means turns can't slow down at the end.
    MIN_MOTOR_OUTPUT = 8
    LOOP_RATE_HZ = 20  # Match BirdBrain HTTP rate

    def __init__(self, finch,
                 headingGains=None,
                 turnGains=None,
                 driveGains=None,
                 compassAverage=None,
                 verbose=False):
        self._finch = finch
        self.headingGains = headingGains or self.DEFAULT_HEADING_GAINS
        self.turnGains    = turnGains    or self.DEFAULT_TURN_GAINS
        self.driveGains   = driveGains   or self.DEFAULT_DRIVE_GAINS
        self.verbose = True

        # Default heading source is encoder-based; pass compassAverage to override.
        # Wheelbase 11.8 cm compensates for carpet wheel slip (was 10.5 cm on
        # smoother surfaces). On carpet the encoders over-count wheel rotation
        # vs actual chassis rotation by ~12%; a larger effective wheelbase
        # makes the kinematic formula report less heading change per encoder
        # tick, cancelling the over-count.
        self._compass = compassAverage or EncoderHeading(finch, wheelbase_cm=11.8)

        self._headingState = self._freshState()
        self._turnState    = self._freshState()
        self._driveState   = self._freshState()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _freshState():
        return {'integral': 0.0, 'prevErr': 0.0, 'lastT': None}

    @staticmethod
    def _resetState(state):
        state['integral'] = 0.0
        state['prevErr'] = 0.0
        state['lastT']   = None

    @staticmethod
    def _shortestAngleDiff(target, current):
        """Signed shortest angle difference (target - current), in (-180, 180].
        Handles 0/359 wraparound."""
        return (target - current + 180) % 360 - 180

    def _pidStep(self, error, gains, state,
                 outputLimits=(-100, 100),
                 integralLimit=30.0,
                 deadband=0.0):
        """One PID iteration. Returns the clamped output."""
        if abs(error) < deadband:
            return 0.0

        kp, ki, kd = gains
        now = time.monotonic()
        dt = (now - state['lastT']) if state['lastT'] is not None else 0.0
        state['lastT'] = now

        if dt > 0:
            state['integral'] += error * dt
            state['integral'] = max(-integralLimit, min(integralLimit, state['integral']))
            derivative = (error - state['prevErr']) / dt
        else:
            derivative = 0.0
        state['prevErr'] = error

        output = kp * error + ki * state['integral'] + kd * derivative
        low, high = outputLimits
        return max(low, min(high, output))

    def _applyMinFloor(self, output):
        """Boost tiny non-zero outputs above the stiction threshold so the
        wheels actually move when the error is small."""
        if 0 < abs(output) < self.MIN_MOTOR_OUTPUT:
            return math.copysign(self.MIN_MOTOR_OUTPUT, output)
        return output

    def _setMotorsTracked(self, left, right):
        """Drive motors AND inform the heading tracker of the commanded
        direction. Always use this instead of self._finch.setMotors()
        directly — for the current EncoderHeading the noteMotorCommand
        call is a no-op, but a different heading source might need it."""
        if hasattr(self._compass, 'noteMotorCommand'):
            self._compass.noteMotorCommand(left, right)
        self._finch.setMotors(left, right)

    def _resetEncodersAndResync(self):
        """Reset BirdBrain encoders for distance tracking, then immediately
        re-baseline the EncoderHeading so it doesn't see the reset as a
        massive phantom motion."""
        self._finch.resetEncoders()
        time.sleep(0.25)  # encoders need a beat to actually zero
        if hasattr(self._compass, 'resyncFromEncoders'):
            self._compass.resyncFromEncoders()

    # ------------------------------------------------------------------
    # Motion primitives
    # ------------------------------------------------------------------
    def turnTo(self, targetHeading, tolerance=None, timeout=None):
        """Rotate in place to an absolute heading.

        PID output is the symmetric wheel speed: positive output means
        left wheel reverses, right wheel forward (left pivot, CCW).
        Returns True if target reached within tolerance, False on timeout.

        If tolerance/timeout are None, uses class constants
        TURN_TOLERANCE_DEG and TURN_TIMEOUT_SEC.
        """
        if tolerance is None:
            tolerance = self.TURN_TOLERANCE_DEG
        if timeout is None:
            timeout = self.TURN_TIMEOUT_SEC

        self._resetState(self._turnState)
        # Don't wipe the heading accumulator — turnTo wants to navigate to
        # an absolute target, not start from 0. Just resync the encoder
        # baselines so the next read sees clean deltas.
        if hasattr(self._compass, 'resyncFromEncoders'):
            self._compass.resyncFromEncoders()
        self._compass.setSize(self.TURN_AVERAGE_SIZE)

        period = 1.0 / self.LOOP_RATE_HZ
        tStart = time.monotonic()
        initial = self._compass.read()
        if self.verbose:
            print(f"[turnTo] target={targetHeading:.1f}  start={initial:.1f}  "
                  f"shortest_diff={self._shortestAngleDiff(targetHeading, initial):.1f}")

        iteration = 0
        try:
            while True:
                current = self._compass.read()
                error = self._shortestAngleDiff(targetHeading, current)

                if abs(error) <= tolerance:
                    self._setMotorsTracked(0, 0)
                    self._finch.stop()
                    if self.verbose:
                        print(f"[turnTo] DONE after {iteration} iters: "
                              f"final={current:.1f}  error={error:.2f}")
                    return True
                if time.monotonic() - tStart > timeout:
                    self._setMotorsTracked(0, 0)
                    self._finch.stop()
                    if self.verbose:
                        print(f"[turnTo] TIMEOUT after {iteration} iters: "
                              f"final={current:.1f}  error={error:.2f}")
                    return False

                speed = self._pidStep(
                    error, self.turnGains, self._turnState,
                    outputLimits=(-self.TURN_OUTPUT_LIMIT, self.TURN_OUTPUT_LIMIT))
                speed_floored = self._applyMinFloor(speed)

                if self.verbose and iteration % 10 == 0:
                    print(f"[turnTo]   iter={iteration} current={current:.1f} "
                          f"err={error:.1f} pid_out={speed:.1f} "
                          f"motors=({-speed_floored:.0f},{speed_floored:.0f})")

                # +error means CCW: left wheel reverses, right wheel forward
                self._setMotorsTracked(speed_floored, -speed_floored)
                time.sleep(period)
                iteration += 1
        finally:
            self._compass.setSize(self.HEADING_AVERAGE_SIZE)

    def driveStraight(self, distanceCm, baseSpeed=None, targetHeading=None):
        """Drive forward <distanceCm> while holding heading via PID.

        Two PID loops run together:
          - Distance loop: signed encoder average -> base forward speed
          - Heading loop:  heading source        -> motor differential

        If targetHeading is None, locks onto current heading at call time.
        If baseSpeed is None, uses DEFAULT_DRIVE_BASE_SPEED.
        Returns signed distance traveled in cm: positive for forward
        drives, negative for reverse.
        """
        if baseSpeed is None:
            baseSpeed = self.DEFAULT_DRIVE_BASE_SPEED

        # Reset encoders for distance tracking, AND resync the heading
        # tracker so it doesn't see this reset as a phantom rotation.
        self._resetEncodersAndResync()
        self._resetState(self._headingState)
        self._resetState(self._driveState)

        self._compass.setSize(self.HEADING_AVERAGE_SIZE)
        # Prime heading source so the first read after this isn't a single
        # noisy measurement. For EncoderHeading these reads are essentially
        # free since the wheels aren't moving.
        for _ in range(self.HEADING_AVERAGE_SIZE):
            self._compass.read()
            time.sleep(0.01)

        if targetHeading is None:
            targetHeading = self._compass.read()

        period = 1.0 / self.LOOP_RATE_HZ
        forward = math.copysign(1, distanceCm)
        targetDist = abs(distanceCm)

        if self.verbose:
            print(f"[driveStraight] target_dist={targetDist:.1f}cm "
                  f"target_heading={targetHeading:.1f} forward={int(forward)}")

        iteration = 0
        while True:
            # Distance feedback: average of signed encoder readings (in cm).
            # For forward drives (forward=+1), signed_traveled grows positive.
            # For reverse drives (forward=-1), it grows negative. The distErr
            # formula projects onto the commanded direction.
            leftRot  = self._finch.getEncoder('L')
            rightRot = self._finch.getEncoder('R')
            signed_traveled = ((leftRot + rightRot) / 2.0) * self.WHEEL_CIRCUMFERENCE_CM
            distErr = forward * (forward * targetDist - signed_traveled)

            if distErr <= self.DRIVE_TOLERANCE_CM:
                self._setMotorsTracked(0, 0)
                self._finch.stop()
                # Return signed distance: positive for forward, negative for reverse.
                return signed_traveled

            # Distance PID: slow down as we approach target
            base = self._pidStep(distErr, self.driveGains, self._driveState,
                                 outputLimits=(0, baseSpeed))

            # Heading PID: differential to add/subtract from each wheel
            headingErr = self._shortestAngleDiff(targetHeading, self._compass.read())
            diff = self._pidStep(
                headingErr, self.headingGains, self._headingState,
                outputLimits=(-self.DRIVE_HEADING_OUTPUT_LIMIT,
                               self.DRIVE_HEADING_OUTPUT_LIMIT),
                deadband=self.HEADING_DEADBAND_DEG)

            left  = forward * base + diff
            right = forward * base - diff
            left  = max(-100, min(100, left))
            right = max(-100, min(100, right))
            self._setMotorsTracked(left, right)
            time.sleep(period)
            iteration += 1

    def holdHeadingStep(self, targetHeading, baseSpeed=None):
        """Run ONE heading-hold update and return immediately.

        Call from your own outer loop (wall-following, web-app tick, etc.)
        when you want continuous forward motion with PID heading correction
        but want to handle the loop yourself.

        If baseSpeed is None, uses DEFAULT_CRUISE_BASE_SPEED.
        Assumes the heading source is already primed — call
        primeForHeadingHold() once before starting your loop.
        """
        if baseSpeed is None:
            baseSpeed = self.DEFAULT_CRUISE_BASE_SPEED

        headingErr = self._shortestAngleDiff(targetHeading, self._compass.read())
        diff = self._pidStep(
            headingErr, self.headingGains, self._headingState,
            outputLimits=(-self.HEADING_OUTPUT_LIMIT, self.HEADING_OUTPUT_LIMIT),
            deadband=self.HEADING_DEADBAND_DEG)
        left  = baseSpeed + diff
        right = baseSpeed - diff
        self._setMotorsTracked(max(-100, min(100, left)),
                               max(-100, min(100, right)))

    def primeForHeadingHold(self):
        """Prepare for a holdHeadingStep loop. Resyncs the encoder baseline
        (so any prior resetEncoders doesn't contaminate the next read) and
        sets the heading-source averaging window for cruise mode."""
        self._resetState(self._headingState)
        if hasattr(self._compass, 'resyncFromEncoders'):
            self._compass.resyncFromEncoders()
        self._compass.setSize(self.HEADING_AVERAGE_SIZE)
        for _ in range(self.HEADING_AVERAGE_SIZE):
            self._compass.read()
            time.sleep(0.01)

    def getAverageHeading(self):
        """Read the current heading without driving the motors. Useful for
        RoomFinch to capture an absolute target before a behavior, or to
        update its internal heading attribute after a turn completes."""
        return self._compass.read()

    def resetAll(self):
        """Reset every internal PID loop AND the heading source. Use when
        transitioning between behaviors."""
        self._resetState(self._headingState)
        self._resetState(self._turnState)
        self._resetState(self._driveState)
        if hasattr(self._compass, 'reset'):
            self._compass.reset()