"""Fill unknown languages with Whisper, leaving audio scores intact."""
import argparse
import fcntl
import json
import subprocess
from pathlib import Path

from moodsync.database import ROOT, db, init_db
from moodsync.library import metadata_lock, write_manifest
from moodsync.language import canonical_language


def run(limit=None):
    init_db()
    data = ROOT / "data"
    data.mkdir(exist_ok=True)
    with (data / "reanalysis.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with db() as connection:
            rows = connection.execute(
                "SELECT id,title,audio_path,metadata_path FROM tracks "
                "WHERE active=1 AND status='ready' AND (language='unknown' OR language='') "
                "ORDER BY artist,title").fetchall()
        if limit is not None:
            rows = rows[:limit]
        found = failed = 0
        with (data / "language-worker.log").open("a") as log:
            worker = subprocess.Popen(
                [str(ROOT / ".ml-venv/bin/python"), "-m", "moodsync.language_worker"],
                cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=log, text=True, bufsize=1)
            try:
                for index, row in enumerate(rows, 1):
                    try:
                        path = Path(row["metadata_path"])
                        with metadata_lock:
                            metadata = json.loads(path.read_text())
                        language = canonical_language(metadata.get("audio_language"))
                        features = {}
                        if not language:
                            worker.stdin.write(json.dumps({"path": row["audio_path"]}) + "\n")
                            worker.stdin.flush()
                            response = worker.stdout.readline()
                            if not response:
                                raise RuntimeError("Language worker stopped; check data/language-worker.log")
                            features = json.loads(response)
                            if "error" in features:
                                raise RuntimeError(features["error"])
                            language = canonical_language(features.get("audio_language"))
                        with metadata_lock:
                            metadata = json.loads(path.read_text())
                            metadata.update(features)
                            if language:
                                metadata["language"] = language
                            temporary = path.with_suffix(".language-tmp")
                            temporary.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
                            temporary.replace(path)
                            if language:
                                with db() as connection:
                                    connection.execute("UPDATE tracks SET language=? WHERE id=?", (language, row["id"]))
                        if language:
                            found += 1
                    except Exception as error:
                        failed += 1
                        print(f"{row['title']}: {error}", flush=True)
                    if index % 25 == 0:
                        write_manifest()
                        print(f"{index}/{len(rows)} checked · {found} identified · {failed} failed", flush=True)
            finally:
                worker.stdin.close()
                worker.wait(timeout=10)
                write_manifest()
        print(f"Done: {found}/{len(rows)} identified; {failed} failed", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None)
    run(parser.parse_args().limit)
