"""Serialize CPU inference through one persistent, isolated ML process."""
import atexit
import json
import os
import select
import subprocess
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "essentia-deam-discogs-whisper-audio-v4"
_lock = threading.Lock()
_worker = None
_log = None


def close():
    global _worker, _log
    if _worker is not None:
        _worker.terminate()
        try:
            _worker.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _worker.kill()
            _worker.wait()
        _worker = None
    if _log is not None:
        _log.close()
        _log = None


atexit.register(close)


def audio_features(path: Path) -> dict:
    global _worker, _log
    with _lock:
        if _worker is None or _worker.poll() is not None:
            close()
            python = Path(os.getenv("MOODSYNC_ML_PYTHON", ROOT / ".ml-venv/bin/python"))
            if not python.is_file():
                raise RuntimeError("ML runtime missing. Install server/requirements-ml.txt with Python 3.12 and run setup_models.py.")
            (ROOT / "data").mkdir(exist_ok=True)
            _log = (ROOT / "data/ml-worker.log").open("a")
            _worker = subprocess.Popen([str(python), str(ROOT / "moodsync/ml_worker.py")],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=_log, text=True, bufsize=1)
        try:
            _worker.stdin.write(json.dumps({"path": str(path.resolve())}) + "\n")
            _worker.stdin.flush()
            ready, _, _ = select.select([_worker.stdout], [], [], 300)
            if not ready:
                raise RuntimeError("Music analysis timed out after five minutes")
            response = _worker.stdout.readline()
            if not response:
                raise RuntimeError("ML worker stopped. Check server/data/ml-worker.log and model installation.")
            result = json.loads(response)
            if "error" in result:
                raise RuntimeError(result["error"])
            return result["features"]
        except Exception:
            close()
            raise
