# MoodSync portable library format v1

The server produces this directory tree. The iOS app accepts either `library/`, `library/tracks/`, or any parent folder containing track directories.

```text
library/
  manifest.json
  tracks/
    PROVIDER__STABLE_ID/
      audio.m4a
      cover.jpg          # optional
      metadata.json
```

`manifest.json` contains `{ "version": 1, "generated_at": "…", "tracks": [...] }`. Each track object and its `metadata.json` use these stable fields:

```json
{
  "id": "provider__stable-id",
  "provider": "manual-or-plugin-id",
  "external_id": "provider-owned stable identifier",
  "title": "Song title",
  "artist": "Artist",
  "album": "Album",
  "language": "en",
  "release_date": "20250131",
  "release_year": 2025,
  "duration": 213.4,
  "valence": 0.63,
  "arousal": 0.81,
  "tempo": 128.0,
  "energy": 0.76,
  "acousticness": 0.12,
  "danceability": 0.71,
  "instrumentalness": 0.08,
  "rhythm_confidence": 0.67,
  "brightness": 0.43,
  "bass_emphasis": 0.72,
  "dynamic_range": 0.31,
  "transient_punch": 0.65,
  "tags": ["Hip Hop", "Rap"],
  "audio": "audio.m4a",
  "artwork": "cover.jpg"
}
```

Mood and sound filter values are library-relative scores from `0...1`; the corresponding original values remain in `raw_*` fields. Language is one base code such as `en`. Unknown optional values may be `null`. Files are self-contained and can be copied over USB without the server database.
