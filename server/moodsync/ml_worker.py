"""Isolated Python 3.12 inference worker. One loaded model set, JSON lines I/O."""
import json
import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("TF_NUM_INTRAOP_THREADS", "2")
os.environ.setdefault("TF_NUM_INTEROP_THREADS", "1")
import numpy as np
from essentia.standard import Resample, RhythmExtractor2013, TensorflowPredictMusiCNN, TensorflowPredict2D, TensorflowPredictEffnetDiscogs
from language_worker import LanguageDetector
from audio_descriptors import describe_audio, sample_clips

ROOT = Path(__file__).resolve().parents[1] / "models"
VERSION = "essentia-deam-discogs-whisper-audio-v4"


class Analyzer:
    def __init__(self):
        self.embedding = TensorflowPredictMusiCNN(graphFilename=str(ROOT / "msd-musicnn-1.pb"), output="model/dense/BiasAdd")
        self.mood = TensorflowPredict2D(graphFilename=str(ROOT / "deam-msd-musicnn-2.pb"), output="model/Identity")
        self.genre_embedding = TensorflowPredictEffnetDiscogs(
            graphFilename=str(ROOT / "discogs-effnet-bs64-1.pb"), output="PartitionedCall:1")
        self.genre_head = TensorflowPredict2D(
            graphFilename=str(ROOT / "genre_discogs400-discogs-effnet-1.pb"),
            input="serving_default_model_Placeholder", output="PartitionedCall:0")
        self.genre_classes = json.loads((ROOT / "genre_discogs400-discogs-effnet-1.json").read_text())["classes"]
        self.language_detector = None
        self.heads = {}
        for field, name, label in [
            ("acousticness", "mood_acoustic", "acoustic"),
            ("danceability", "danceability", "danceable"),
            ("instrumentalness", "voice_instrumental", "instrumental"),
        ]:
            stem = f"{name}-msd-musicnn-1"
            metadata = json.loads((ROOT / f"{stem}.json").read_text())
            self.heads[field] = (
                TensorflowPredict2D(graphFilename=str(ROOT / f"{stem}.pb"), output="model/Softmax"),
                metadata["classes"].index(label),
            )

    def analyze(self, path):
        clips = sample_clips(path)
        embeddings = np.concatenate([self.embedding(clip) for clip in clips])
        scores = np.mean(self.mood(embeddings), axis=0)
        valence, arousal = np.clip((scores - 1) / 8, 0, 1)
        audio = np.concatenate(clips)
        sound = describe_audio(audio)
        rms = float(np.sqrt(np.mean(audio * audio)))
        # Energy is explicit recording loudness, not emotion: -50..0 dBFS maps to 0..1.
        energy = float(np.clip((20 * np.log10(max(rms, 1e-8)) + 50) / 50, 0, 1))
        rhythm_audio = Resample(inputSampleRate=16000, outputSampleRate=44100)(audio)
        tempo, _, confidence, _, _ = RhythmExtractor2013(method="multifeature")(rhythm_audio)
        result = {"valence": float(valence), "arousal": float(arousal), "energy": energy,
                  "tempo": float(tempo), "tempo_confidence": float(confidence),
                  "rhythm_confidence": float(confidence)}
        for field, (model, index) in self.heads.items():
            result[field] = float(np.mean(model(embeddings), axis=0)[index])
        genre_embeddings = np.concatenate([self.genre_embedding(clip) for clip in clips])
        genre_scores = np.mean(self.genre_head(genre_embeddings), axis=0)
        best = np.argsort(genre_scores)[::-1][:3]
        styles = [self.genre_classes[int(i)] for i in best
                  if genre_scores[int(i)] >= max(.015, float(genre_scores[int(best[0])]) * .3)]
        if not styles:
            styles = [self.genre_classes[int(best[0])]]
        tags = []
        for style in styles:
            parent, _, specific = style.partition("---")
            for tag in (parent, "Rap" if "rap" in specific.casefold() else "", specific):
                if tag and tag not in tags:
                    tags.append(tag)
        result["genre_confidence"] = float(genre_scores[int(best[0])])
        try:
            if self.language_detector is None:
                self.language_detector = LanguageDetector()
            # Give Whisper three full excerpts. Three ten-second excerpts form
            # only one detection window and can miss vocals between them.
            result.update(self.language_detector.detect_clips(clips))
        except Exception as error:
            print(f"Audio language detection skipped: {error}", file=sys.stderr, flush=True)
        if not all(np.isfinite(value) for value in result.values()
                   if isinstance(value, (int, float, np.floating))):
            raise ValueError("Model returned non-finite audio features")
        return {**{key: round(value, 4) if isinstance(value, (float, np.floating)) else value
                   for key, value in result.items()}, **sound, "genre_styles": styles, "tags": tags,
                "analysis_model": VERSION, "analysis_samples": len(clips)}


if __name__ == "__main__":
    analyzer = Analyzer()
    for line in sys.stdin:
        try:
            request = json.loads(line)
            response = {"features": analyzer.analyze(request["path"])}
        except Exception as error:
            response = {"error": f"{type(error).__name__}: {error}"}
        print(json.dumps(response), flush=True)
