"""Whisper language inference for existing audio, without rerunning mood models."""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from faster_whisper import WhisperModel
try:
    from .audio_descriptors import sample_clips
except ImportError:  # Invoked directly by the inference worker.
    from audio_descriptors import sample_clips

ROOT = Path(__file__).resolve().parents[1] / "models"


class LanguageDetector:
    def __init__(self):
        self.model = WhisperModel(str(ROOT / "whisper-tiny"), device="cpu", compute_type="int8")

    def detect_clips(self, clips):
        sample = np.concatenate(clips)
        candidate, confidence, _ = self.model.detect_language(
            sample, language_detection_segments=min(3, len(clips)),
            language_detection_threshold=.8)
        return {"audio_language_confidence": round(float(confidence), 4),
                "audio_language": candidate if confidence >= .65 else None}

    def detect_file(self, path):
        return self.detect_clips(sample_clips(path))


if __name__ == "__main__":
    detector = LanguageDetector()
    for line in sys.stdin:
        try:
            result = detector.detect_file(json.loads(line)["path"])
        except Exception as error:
            result = {"error": f"{type(error).__name__}: {error}"}
        print(json.dumps(result), flush=True)
