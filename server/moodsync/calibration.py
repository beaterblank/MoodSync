"""Library-relative display scales; raw model scores remain in metadata."""
from bisect import bisect_left, bisect_right
from math import isfinite

FIELDS = ("valence", "arousal", "danceability", "energy", "acousticness", "instrumentalness", "rhythm_confidence",
          "brightness", "bass_emphasis", "dynamic_range", "transient_punch")
VERSION = "library-percentile-v1"


def calibrate(rows: list[dict]) -> list[dict]:
    ordered = {}
    for field in FIELDS:
        values = [row.get("raw_" + field, row.get(field)) for row in rows]
        ordered[field] = sorted(value for value in values
                                if isinstance(value, (int, float)) and isfinite(value))
    result = []
    for original in rows:
        row = dict(original)
        for field in FIELDS:
            raw = row.get("raw_" + field, row.get(field))
            if not isinstance(raw, (int, float)) or not isfinite(raw):
                continue
            row["raw_" + field] = round(float(raw), 4)
            values = ordered[field]
            if len(values) < 10:
                row[field] = round(float(raw) / (1 + max(0, float(raw))) if field == "rhythm_confidence"
                                   else float(raw), 4)
                continue
            left, right = bisect_left(values, raw), bisect_right(values, raw)
            rank = ((left + right - 1) / 2) / (len(values) - 1)
            row[field] = round(.02 + .96 * rank, 4)
        row["display_scaling"] = VERSION
        result.append(row)
    return result
