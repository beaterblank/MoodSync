"""Download versioned Essentia weights and metadata; audio stays on this computer."""
import hashlib
import json
import subprocess
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent / "models"
MODELS = {
    "msd-musicnn-1": "autotagging/msd/msd-musicnn-1",
    "deam-msd-musicnn-2": "classification-heads/deam/deam-msd-musicnn-2",
    "mood_acoustic-msd-musicnn-1": "classification-heads/mood_acoustic/mood_acoustic-msd-musicnn-1",
    "danceability-msd-musicnn-1": "classification-heads/danceability/danceability-msd-musicnn-1",
    "voice_instrumental-msd-musicnn-1": "classification-heads/voice_instrumental/voice_instrumental-msd-musicnn-1",
    "discogs-effnet-bs64-1": "feature-extractors/discogs-effnet/discogs-effnet-bs64-1",
    "genre_discogs400-discogs-effnet-1": "classification-heads/genre_discogs400/genre_discogs400-discogs-effnet-1",
}

if __name__ == "__main__":
    ROOT.mkdir(exist_ok=True)
    records = {}
    for name, remote in MODELS.items():
        for extension in ("json", "pb"):
            target = ROOT / f"{name}.{extension}"
            url = f"https://essentia.upf.edu/models/{remote}.{extension}"
            if not target.exists():
                with urlopen(url, timeout=120) as response:
                    data = response.read()
                if extension == "json":
                    json.loads(data)
                temporary = target.with_suffix(".download")
                temporary.write_bytes(data)
                temporary.replace(target)
            records[target.name] = {"url": url, "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
            print(target.name, flush=True)
    (ROOT / "downloads.json").write_text(json.dumps(records, indent=2))
    # The small multilingual Whisper model identifies vocal language from audio.
    whisper = ROOT / "whisper-tiny"
    if not (whisper / "model.bin").is_file():
        subprocess.run([str(ROOT.parent / ".ml-venv/bin/python"), "-c",
                        "from faster_whisper.utils import download_model; download_model('tiny', output_dir=" + repr(str(whisper)) + ")"], check=True)
    print("whisper-tiny", flush=True)
