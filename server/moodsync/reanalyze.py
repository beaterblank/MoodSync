"""Resumable local reanalysis, with pause/resume and visible per-track stages."""
import fcntl
import json
import logging
import threading
import time
from pathlib import Path

from .analysis import VERSION, audio_features
from .database import ROOT, db
from .library import LEGACY_LYRIC_FIELDS, metadata_lock, now, write_manifest
from .language import canonical_language

STATUS = ROOT / "data/reanalysis.json"
_pause = threading.Event()
_worker = None
_control = threading.Lock()


def status():
    try:
        progress = json.loads(STATUS.read_text())
        processed = progress.get("completed", 0) + progress.get("failed", 0)
        total = progress.get("total", 0)
        elapsed = max(0, time.time() - progress.get("started_at", time.time()))
        progress["elapsed_seconds"] = round(elapsed)
        progress["eta_seconds"] = (round(elapsed / processed * (total - processed))
                                   if progress.get("state") in {"running", "pausing"} and processed else None)
        progress["percent"] = round(100 * processed / total) if total else 0
        return progress
    except (OSError, ValueError):
        return {"state": "idle", "completed": 0, "total": 0, "failed": 0}


def _save(progress):
    STATUS.parent.mkdir(exist_ok=True)
    temporary = STATUS.with_suffix(".tmp")
    temporary.write_text(json.dumps(progress))
    temporary.replace(STATUS)


def _stage(track_id, stage, fraction):
    with db() as c:
        c.execute("UPDATE tracks SET analysis_status=?,analysis_progress=?,analysis_error=NULL WHERE id=?",
                  (stage, fraction, track_id))


def _pending_rows(rows, force=False):
    pending = []
    for row in rows:
        try:
            metadata = json.loads(Path(row["metadata_path"]).read_text())
            if force or not str(metadata.get("analysis_model") or "").startswith(VERSION):
                pending.append(row)
        except (OSError, ValueError, TypeError):
            continue
    return pending


def rebuild(force=False, resume=None):
    STATUS.parent.mkdir(exist_ok=True)
    with (STATUS.parent / "reanalysis.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        with db() as c:
            rows = c.execute("SELECT id,title,audio_path,metadata_path FROM tracks WHERE active=1 AND status='ready'").fetchall()
        pending = _pending_rows(rows, force)
        mode = "all" if force else "unfinished"
        progress = ({**resume, "state": "running", "current": "", "stage": ""}
                    if resume and resume.get("mode") == mode and resume.get("model") == VERSION else
                    {"state": "running", "completed": 0, "failed": 0,
                     "total": len(pending), "model": VERSION, "current": "", "mode": mode,
                     "started_at": time.time(), "processed_ids": []})
        processed_ids = set(progress.get("processed_ids", []))
        _save(progress)
        for row in pending:
            if row["id"] in processed_ids:
                continue
            if _pause.is_set():
                progress["state"] = "paused"
                _save(progress)
                return
            track_id = row["id"]
            progress["current"] = row["title"]
            progress["current_id"] = track_id
            progress["stage"] = "Analyzing audio"
            _save(progress)
            try:
                _stage(track_id, "analyzing audio", .1)
                features = audio_features(Path(row["audio_path"]))
                _stage(track_id, "saving metadata", .95)
                progress["stage"] = "Saving metadata"
                _save(progress)
                with metadata_lock:
                    with db() as c:
                        live = c.execute("SELECT status,active FROM tracks WHERE id=?", (track_id,)).fetchone()
                        if not live or not live["active"] or live["status"] != "ready":
                            continue
                        path = Path(row["metadata_path"])
                        original = path.read_text()
                        metadata = json.loads(original)
                        backup = path.with_name("metadata.pre-ml.json")
                        if not backup.exists():
                            backup.write_text(original)
                        for key in LEGACY_LYRIC_FIELDS:
                            metadata.pop(key, None)
                        metadata.update(features)
                        language = canonical_language(features.get("audio_language")) or canonical_language(metadata.get("language"))
                        metadata["language"] = language
                        for field in ("valence", "arousal", "danceability", "energy", "acousticness", "instrumentalness", "rhythm_confidence", "brightness", "bass_emphasis", "dynamic_range", "transient_punch"):
                            if field in features:
                                metadata["raw_" + field] = features[field]
                        temporary = path.with_suffix(".ml-tmp")
                        temporary.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
                        temporary.replace(path)
                        c.execute("""UPDATE tracks SET valence=?,arousal=?,tempo=?,energy=?,acousticness=?,language=?,tags=?,
                            analysis_status='complete',analysis_progress=1,analysis_error=NULL,updated_at=? WHERE id=?""",
                            (features["valence"], features["arousal"], features["tempo"], features["energy"],
                             features["acousticness"], language or "unknown", json.dumps(features.get("tags", [])),
                             now(), track_id))
                progress["completed"] += 1
                progress["processed_ids"].append(track_id)
                if progress["completed"] % 10 == 0:
                    write_manifest()
            except Exception as error:
                progress["failed"] += 1
                progress["processed_ids"].append(track_id)
                progress["last_error"] = str(error)
                with db() as c:
                    c.execute("UPDATE tracks SET analysis_status='failed',analysis_error=? WHERE id=?",
                              (str(error)[:2000], track_id))
                logging.exception("Reanalysis failed for %s", track_id)
            _save(progress)
        write_manifest()
        progress["state"] = "complete" if not progress["failed"] else "complete_with_errors"
        progress["current"] = ""
        progress["stage"] = ""
        _save(progress)


def start(force=False):
    global _worker
    with _control:
        if _worker is None or not _worker.is_alive():
            _pause.clear()
            previous = status()
            if previous.get("state") == "paused" and not force:
                force = previous.get("mode") == "all"
            resume = previous if previous.get("state") == "paused" and previous.get("mode") == ("all" if force else "unfinished") else None
            _save({**previous, "state": "starting", "current": "", "stage": "", "last_error": ""})
            _worker = threading.Thread(target=rebuild, kwargs={"force": force, "resume": resume}, daemon=True, name="mood-reanalysis")
            _worker.start()
        else:
            progress = status()
            if progress["state"] in {"paused", "pausing"}:
                _pause.clear()
                progress["state"] = "running"
                _save(progress)
    return status()


def pause():
    _pause.set()
    progress = status()
    if progress["state"] in {"running", "starting"}:
        progress["state"] = "pausing"
        _save(progress)
    return progress


def restore():
    previous = status()
    if previous["state"] == "paused":
        return
    if previous["state"] in {"starting", "running", "pausing"}:
        start(force=previous.get("mode") == "all")
    else:
        start()


if __name__ == "__main__":
    from .database import init_db
    init_db()
    rebuild()
    print(json.dumps(status()))
