import unittest

import numpy as np

from moodsync.audio_descriptors import describe_audio


class AudioDescriptorTests(unittest.TestCase):
    def test_low_and_high_tones_separate_bass_and_brightness(self):
        time = np.arange(16000 * 4) / 16000
        bass = describe_audio(np.sin(2 * np.pi * 100 * time).astype(np.float32))
        treble = describe_audio(np.sin(2 * np.pi * 3000 * time).astype(np.float32))
        self.assertGreater(bass["bass_emphasis"], treble["bass_emphasis"])
        self.assertLess(bass["brightness"], treble["brightness"])
        self.assertTrue(all(0 <= value <= 1 for value in bass.values()))


if __name__ == "__main__":
    unittest.main()
