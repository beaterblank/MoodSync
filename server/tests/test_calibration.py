import unittest

from moodsync.calibration import calibrate


class CalibrationTests(unittest.TestCase):
    def test_narrow_model_scores_fill_display_range_without_losing_raw_scores(self):
        tracks = [{"id": str(i), "danceability": .9 + i * .001,
                   "valence": .45 + i * .002, "arousal": .5 + i * .001} for i in range(20)]
        scaled = calibrate(tracks)
        self.assertEqual(scaled[0]["raw_danceability"], .9)
        self.assertEqual(scaled[-1]["raw_danceability"], .919)
        self.assertAlmostEqual(scaled[0]["danceability"], .02)
        self.assertAlmostEqual(scaled[-1]["danceability"], .98)
        self.assertEqual(calibrate(scaled), scaled)


if __name__ == "__main__":
    unittest.main()
