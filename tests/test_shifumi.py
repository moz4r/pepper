import unittest
import time
import sys
import types

# The shifumi module depends on the 'qi' package which isn't available in the
# execution environment.  Provide a simple stub so that the module can be
# imported for unit testing purposes.
sys.modules.setdefault('qi', types.ModuleType('qi'))

from jeux.shifumi import geste_shifumi


class FakeMotion:
    """Simplified mock of ALMotion used for testing."""

    def __init__(self):
        self.angle_calls = []
        self.speed_calls = []

    def angleInterpolation(self, names, angles, times, is_absolute):
        self.angle_calls.append((names, angles, times, is_absolute))

    def angleInterpolationWithSpeed(self, *args, **kwargs):
        self.speed_calls.append((args, kwargs))


class GesteShifumiTest(unittest.TestCase):
    def test_shake_uses_increasing_timelines(self):
        motion = FakeMotion()

        # Patch time.time to simulate only a single iteration of the loop
        seq = iter([0, 1, 2])
        original_time = time.time
        time.time = lambda: next(seq)
        try:
            geste_shifumi(motion, "pierre")
        finally:
            time.time = original_time

        self.assertGreaterEqual(len(motion.angle_calls), 2)
        for _, _, timelines, _ in motion.angle_calls:
            # timelines is a list with a single list inside for each joint
            times = timelines[0]
            self.assertTrue(all(t2 > t1 for t1, t2 in zip(times, times[1:])))


if __name__ == "__main__":
    unittest.main()
