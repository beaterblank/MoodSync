"""Calculate new local sound filters without rerunning mood and genre models."""
import argparse
import fcntl
import json
import logging
from pathlib import Path

import numpy as np

from moodsync.audio_descriptors import describe_audio, sample_clips
from moodsync.database import ROOT, db, init_db
from moodsync.library import metadata_lock, write_manifest

FIELDS = ("brightness", "bass_emphasis", "dynamic_range", "transient_punch")


def run(limit=None):
    init_db()
    data = ROOT / "data"
    data.mkdir(exist_ok=True)
    with (data / "reanalysis.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with db() as connection:
            rows = connection.execute(
                "SELECT id,title,audio_path,metadata_path FROM tracks "
                "WHERE active=1 AND status='ready' ORDER BY artist,title").fetchall()
        pending = []
        for row in rows:
            try:
                metadata = json.loads(Path(row["metadata_path"]).read_text())
                if any(field not in metadata for field in FIELDS):
                    pending.append(row)
            except (OSError, ValueError, TypeError):
                logging.exception("Could not read metadata for %s", row["id"])
        if limit is not None:
            pending = pending[:limit]
        completed = failed = 0
        try:
            for index, row in enumerate(pending, 1):
                try:
                    sound = describe_audio(np.concatenate(sample_clips(row["audio_path"])))
                    with metadata_lock:
                        path = Path(row["metadata_path"])
                        metadata = json.loads(path.read_text())
                        metadata.update(sound)
                        metadata.update({"raw_" + key: value for key, value in sound.items()})
                        temporary = path.with_suffix(".sound-tmp")
                        temporary.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
                        temporary.replace(path)
                    completed += 1
                except Exception as error:
                    failed += 1
                    print(f"{row['title']}: {error}", flush=True)
                if index % 25 == 0:
                    write_manifest()
                    print(f"{index}/{len(pending)} checked · {completed} analyzed · {failed} failed", flush=True)
        finally:
            write_manifest()
        print(f"Done: {completed}/{len(pending)} analyzed; {failed} failed", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None)
    run(parser.parse_args().limit)
