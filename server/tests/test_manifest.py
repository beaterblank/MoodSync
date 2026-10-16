import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from moodsync import database, library


class ManifestCalibrationTests(unittest.TestCase):
    def test_manifest_and_database_use_relative_values_with_raw_metadata_retained(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            tracks = root / "library/tracks"
            tracks.mkdir(parents=True)
            with patch.object(database, "DB_PATH", root / "data.sqlite3"), \
                 patch.object(library, "LIBRARY", root / "library"), \
                 patch.object(library, "TRACKS", tracks):
                database.init_db()
                with database.db() as connection:
                    for index in range(20):
                        track_id = f"song-{index}"
                        metadata_path = tracks / track_id / "metadata.json"
                        metadata_path.parent.mkdir()
                        metadata_path.write_text(json.dumps({
                            "id": track_id, "title": track_id, "artist": "Artist",
                            "language": "en-US" if index == 0 else "en",
                            "tags": ["Hip Hop", "Trap"], "lyrics_lookup_status": "found",
                            "valence": .45 + index * .001, "arousal": .5 + index * .001,
                            "danceability": .9 + index * .001, "energy": .8,
                            "brightness": .2 + index * .001,
                        }))
                        connection.execute(
                            "INSERT INTO tracks(id,title,artist,status,metadata_path,created_at,updated_at) "
                            "VALUES(?,?,?,'ready',?,?,?)",
                            (track_id, track_id, "Artist", str(metadata_path), "now", "now"))
                library.write_manifest()
                manifest = json.loads((root / "library/manifest.json").read_text())
                self.assertAlmostEqual(manifest["tracks"][0]["danceability"], .02)
                self.assertEqual(manifest["tracks"][0]["raw_danceability"], .9)
                self.assertEqual({row["language"] for row in manifest["tracks"]}, {"en"})
                self.assertNotIn("lyrics_lookup_status", manifest["tracks"][0])
                self.assertAlmostEqual(manifest["tracks"][0]["brightness"], .02)
                with database.db() as connection:
                    row = connection.execute("SELECT tags,valence FROM tracks WHERE id='song-0'").fetchone()
                self.assertEqual(json.loads(row["tags"]), ["Hip Hop", "Trap"])
                self.assertAlmostEqual(row["valence"], .02)


if __name__ == "__main__":
    unittest.main()
