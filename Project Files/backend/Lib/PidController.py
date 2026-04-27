"""
PID Controller
Implements a PID Controller for the finch to more accurate control over where it is going
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
        new_size = max(1, size)
        if new_size == self._buffer.maxlen:
            return
        self._buffer = deque(self._buffer, maxlen=new_size)
 
    def reset(self):
        """Discard all buffered samples. Call when transitioning between behaviors so a stale buffer doesn't bias the next reading."""
        self._buffer.clear()
 
    def read(self):
        """Take one fresh compass reading, push it into the buffer, return the circular mean of the buffer in degrees [0, 360)."""
        raw_deg = self._finch.getCompass()
        self._buffer.append(math.radians(raw_deg))
 
        mean_sin = sum(math.sin(a) for a in self._buffer) / len(self._buffer)
        mean_cos = sum(math.cos(a) for a in self._buffer) / len(self._buffer)
        mean_rad = math.atan2(mean_sin, mean_cos)
        return math.degrees(mean_rad) % 360

