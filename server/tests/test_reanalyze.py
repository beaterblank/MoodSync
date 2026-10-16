import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from moodsync.analysis import VERSION
from moodsync import database, reanalyze
from moodsync.reanalyze import _pending_rows


class ReanalysisSelectionTests(unittest.TestCase):
    def test_manual_start_includes_already_analyzed_tracks(self):
        with tempfile.TemporaryDirectory() as folder:
            old = Path(folder) / "old.json"
            current = Path(folder) / "current.json"
            old.write_text(json.dumps({"analysis_model": "legacy"}))
            current.write_text(json.dumps({"analysis_model": VERSION}))
            rows = [{"metadata_path": str(old)}, {"metadata_path": str(current)}]
            self.assertEqual(_pending_rows(rows, force=False), rows[:1])
            self.assertEqual(_pending_rows(rows, force=True), rows)

    def test_rebuild_saves_audio_descriptors_and_removes_legacy_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            metadata_path = root / "metadata.json"
            metadata_path.write_text(json.dumps({
                "id": "song", "title": "Song", "artist": "Artist", "valence": .95,
                "raw_valence": .3, "arousal": .9, "raw_arousal": .4,
                "energy": .8, "raw_energy": .5, "acousticness": .6,
                "raw_acousticness": .2, "tempo": 120, "lyrics_lookup_status": "unavailable",
                "analysis_model": VERSION,
            }))
            features = {"valence": .3, "arousal": .4, "energy": .5,
                        "acousticness": .2, "tempo": 120, "brightness": .7,
                        "bass_emphasis": .3, "dynamic_range": .4,
                        "transient_punch": .6, "tags": ["Rock"],
                        "analysis_model": VERSION}
            with patch.object(database, "DB_PATH", root / "test.sqlite3"), \
                 patch.object(reanalyze, "STATUS", root / "status.json"), \
                 patch.object(reanalyze, "write_manifest"), \
                 patch.object(reanalyze, "audio_features", return_value=features):
                database.init_db()
                with database.db() as connection:
                    connection.execute(
                        "INSERT INTO tracks(id,title,artist,status,active,audio_path,metadata_path,duration,provider,created_at,updated_at) "
                        "VALUES('song','Song','Artist','ready',1,?,?,180,'youtube','now','now')",
                        (str(root / "audio.m4a"), str(metadata_path)))
                reanalyze.rebuild(force=True)
                updated = json.loads(metadata_path.read_text())
                self.assertEqual(updated["raw_valence"], .3)
                self.assertEqual(updated["raw_arousal"], .4)
                self.assertEqual(updated["valence"], .3)
                self.assertEqual(updated["brightness"], .7)
                self.assertEqual(updated["raw_brightness"], .7)
                self.assertNotIn("lyrics_lookup_status", updated)
                self.assertEqual(reanalyze.status()["completed"], 1)


if __name__ == "__main__":
    unittest.main()
