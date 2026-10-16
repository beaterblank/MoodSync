# Acquisition plugin contract

MoodSync core never knows how provider media is obtained. A plugin may talk to a service API, watch an export folder, copy owned files, or perform another authorized acquisition workflow. It only operates in a per-job staging directory.

## Directory

Place plugins under `server/plugins/<plugin-id>/` or add external roots with `MOODSYNC_PLUGIN_DIRS` (colon-separated on Linux):

```text
my-provider/
  plugin.json
  plugin.py
  requirements.txt   # optional and installed separately
```

The manifest declares provider-agnostic UI fields:

```json
{
  "api_version": 1,
  "id": "my-provider",
  "name": "My provider",
  "description": "Imports owned files from My provider",
  "module": "plugin.py",
  "fields": [
    {"name": "collection", "label": "Collection URL", "type": "url", "required": true}
  ]
}
```

## Python interface

`plugin.py` exports `Plugin` with two methods:

```python
from moodsync.plugins import AcquisitionPlugin, SourceSnapshot

class Plugin(AcquisitionPlugin):
    def inspect(self, config):
        # Return the current remote/source snapshot. external_id must be stable.
        return SourceSnapshot("Collection title", [
            {"external_id": "stable-id", "title": "Display title", "opaque": "plugin-owned data"}
        ])

    def acquire(self, entry, destination, progress):
        # Write only inside destination. Core validates all returned paths.
        # The source may be any audio container FFmpeg can read.
        progress(0.25, "Copying authorized media")
        write_audio(destination / "source.flac")
        return {
            "audio": "source.flac",
            "artwork": "cover.png",  # optional
            "metadata": {
                "title": "Title", "artist": "Artist", "album": "Album",
                "language": "en", "release_date": "20250101", "duration": 180
            }
        }
```

The core then, without trusting the plugin:

1. rejects paths outside that job's staging directory;
2. transcodes audio to the canonical M4A format;
3. normalizes artwork;
4. computes valence, arousal, tempo, energy, and acousticness;
5. writes canonical metadata and atomically installs the track;
6. updates SQLite and the device manifest.

Plugins cannot choose final paths or write directly to the organized library through this API. Removing a plugin prevents new acquisition/refresh jobs but does not affect already normalized tracks.

## Git discovery and lifecycle

Clone a plugin Git repository directly into `server/plugin-repos/<plugin-id>`, where `<plugin-id>` matches the `id` in its root `plugin.json`. This directory is ignored by the MoodSync repository. Restart the server or choose **Reload plugins** to discover it. Install any plugin-specific Python dependencies from that clone into the server environment.

The dashboard's **Plugins** screen also accepts a Git URL or an absolute path to a local Git repository. A repository must have `plugin.json` at its root and must declare the current `api_version`. MoodSync clones it under `server/plugin-repos/<plugin-id>`, validates the manifest and module location, verifies that `Plugin` subclasses `AcquisitionPlugin`, and only then makes it selectable.

Managed repositories, including direct clones, can be updated with a fast-forward-only pull or uninstalled in the UI. A plugin cannot be uninstalled while a configured source still uses it. External directories configured with `MOODSYNC_PLUGIN_DIRS` are discovered and reloaded but never modified by MoodSync.

Installing a plugin is equivalent to installing and running trusted Python software. The ABC and path validation define compatibility and protect the final library layout; they are not a security sandbox.
