"""Fast, interpretable descriptors from the same excerpts used by the models."""
import numpy as np
import subprocess


def sample_clips(path) -> list[np.ndarray]:
    """Decode three representative excerpts once for all local sound features."""
    duration = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)], capture_output=True,
        text=True, check=True).stdout.strip())
    positions = [0] if duration <= 90 else [duration * .15, duration * .5,
                                            max(0, duration * .85 - 30)]
    clips = []
    for position in positions:
        data = subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", str(position), "-i", str(path),
             "-t", str(min(duration, 90) if len(positions) == 1 else 30),
             "-ac", "1", "-ar", "16000", "-f", "f32le", "pipe:1"],
            capture_output=True, check=True).stdout
        clip = np.frombuffer(data, dtype=np.float32).copy()
        if len(clip) >= 16000 * 3:
            clips.append(clip)
    if not clips:
        raise ValueError("Audio is too short for sound analysis")
    return clips


def describe_audio(audio: np.ndarray, sample_rate: int = 16000) -> dict[str, float]:
    size, hop = 2048, 1024
    if len(audio) < size:
        raise ValueError("Audio is too short for sound descriptors")
    frames = np.lib.stride_tricks.sliding_window_view(audio, size)[::hop]
    window = np.hanning(size).astype(np.float32)
    spectrum = np.abs(np.fft.rfft(frames * window, axis=1))
    power = spectrum ** 2
    frequencies = np.fft.rfftfreq(size, 1 / sample_rate)
    total = np.maximum(power.sum(axis=1), 1e-10)
    centroid = (power * frequencies).sum(axis=1) / total
    brightness = float(np.clip(np.median(centroid) / 5000, 0, 1))
    bass = float(np.clip(np.median(power[:, (frequencies >= 40) & (frequencies < 250)].sum(axis=1)
                                   / total), 0, 1))
    rms = np.sqrt(np.maximum(np.mean(frames ** 2, axis=1), 1e-12))
    active = rms > max(1e-4, np.percentile(rms, 20))
    db = 20 * np.log10(np.maximum(rms[active], 1e-6))
    dynamics = float(np.clip((np.percentile(db, 90) - np.percentile(db, 10)) / 30, 0, 1)) if len(db) else 0
    normalized = spectrum / np.maximum(spectrum.sum(axis=1, keepdims=True), 1e-10)
    flux = np.maximum(0, np.diff(normalized, axis=0)).sum(axis=1)
    punch = float(np.clip(np.percentile(flux, 90) / .6, 0, 1)) if len(flux) else 0
    return {"brightness": round(brightness, 4), "bass_emphasis": round(bass, 4),
            "dynamic_range": round(dynamics, 4), "transient_punch": round(punch, 4)}
