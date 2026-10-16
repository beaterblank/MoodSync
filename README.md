# MoodSync

MoodSync is a private music pipeline with two parts:

- A provider-agnostic FastAPI core that accepts local audio or staged output from acquisition plugins, analyses it with FFmpeg/NumPy, organizes it, tracks everything in SQLite, reconciles plugin sources, and exposes a portable library.
- A SwiftUI iPhone player that imports the same library over Wi-Fi or through Files/USB, plays offline with lock-screen controls, and finds songs by distance from an interactive valence/arousal point plus artist, language, year, energy, and acousticness filters.

The core contains no YouTube, Spotify, or downloader integration. Acquisition plugins are independently installable adapters with separate dependencies and policies. Only use a plugin for media you have the rights and provider permission to acquire.

## Local server

Requirements: Python 3.11+ and `ffmpeg`. No provider/downloader package is installed by the core requirements.

```bash
cd server
cp .env.example .env
chmod +x run.sh
./run.sh
```

Open `http://localhost:8088`. Other devices on the same LAN use `http://YOUR-COMPUTER-IP:8088`.

For private Wi-Fi sync, put a random value in `.env`:

```bash
MOODSYNC_SYNC_TOKEN=a-long-random-token
```

Enter the same token in the iPhone sync screen. The management dashboard is intended only for a trusted local network; do not expose port 8088 to the public internet.

Plugin sources are reconciled whenever you press **Refresh** and automatically every 30 minutes by default (`MOODSYNC_SYNC_INTERVAL_MINUTES`). New items are queued through their acquisition plugin. With **Mirror deletions** enabled, a removed item is deleted locally only when no other active source still contains it.

Acquisition and analysis run concurrently. MoodSync selects 4–12 workers from the machine's CPU count; override this with `MOODSYNC_WORKERS`. The Library screen provides **Retry all failed** for bulk recovery after a provider or network problem.

You can also upload a local audio file from the dashboard. It enters the same core transcoding and analysis pipeline without using a plugin.

## Acquisition plugins

Plugins are separate Git repositories cloned into the ignored `server/plugin-repos/` directory, or discovered read-only from directories listed by `MOODSYNC_PLUGIN_DIRS`. The dashboard builds source forms from each plugin manifest, so it contains no provider-specific UI code.

Clone the YouTube adapter into its manifest ID directory from the MoodSync repository root:

```bash
git clone https://github.com/beaterblank/MoodSyncYouTubePlugin.git server/plugin-repos/youtube
server/.venv/bin/pip install -r server/plugin-repos/youtube/requirements.txt
```

Restart the server or choose **Reload plugins** in the dashboard. The adapter's dependency is deliberately absent from the core requirements. The dashboard's **Install repository** action can also clone a local path or Git URL into the same ignored directory.

See [PLUGINS.md](PLUGINS.md) for the stable interface used to add a future Spotify export, watched folder, purchased-music service, or another authorized source.

## iPhone app

The SwiftUI package in `ios/` follows the `xtool` layout used by `omarchy-apple-dev`.

```bash
cd ios
xtool dev build
```

To install on a connected iPhone from the project directory:

```bash
/path/to/omarchy-apple-dev/device-run.sh
```

The Linux toolchain and matching Apple SDK must already be installed with `omarchy-apple-dev/install-toolchain.sh`. Run all build and deployment commands from `ios/`, where `Package.swift` lives.

### Transfer methods

- **Wi-Fi:** start or restart `server/run.sh`, connect both devices to the same Wi-Fi, and open the app's Sync screen. Allow Local Network access when iOS asks. The server advertises `_moodsync._tcp` through Bonjour; the app resolves it and verifies `/api/device/health` before showing **Connected**. Tap **Sync music**. Only protected libraries ask for a sync key; addresses are not shown. Set `MOODSYNC_SERVER_NAME` in the server's `.env` to choose the displayed library name.
- Bonjour discovery works on networks that permit multicast DNS and access to the server port. If discovery fails, check Wi-Fi isolation and the computer's firewall. The server currently advertises its IPv4 LAN addresses. Background file downloads continue when the app is suspended, subject to iOS scheduling and network availability.
- **Files/USB:** copy `server/library/tracks` into Files, then choose **Choose a MoodSync folder** in the sync screen.
- Interrupted syncs reuse downloaded audio and artwork on retry. The new manifest is applied only after required downloads complete. Previously downloaded files remain on disk even when absent from the new manifest.

### Browse and play

- **Discover** keeps the mood graph. Drag to move the target; hold for 0.45 seconds, or tap **Fine-tune**, to adjust valence, arousal and radius in 0.001 increments and change each axis's ranking weight.
- **Songs** shares the mood and filters, with title/artist/album search, Play, Shuffle, artwork, metadata, duration and the current playback indicator.
- Filters support multiple artists, languages, albums, and model generated genres/styles, plus bounds for year, tempo, energy, acousticness, danceability, instrumentalness, beat strength, brightness, bass emphasis, dynamic range, transient punch, valence, arousal, and duration. Empty selections include all values; selections within a category use OR, and different categories combine with AND. Missing metadata can be included or excluded.
- Sort by mood distance, title, artist, album, year, tempo, duration, energy, acousticness, danceability, instrumentalness, valence, arousal, beat strength, brightness, bass emphasis, dynamic range, or transient punch. Missing numeric sort values stay last. The mini player opens full playback controls; playback advances through the chosen queue.

Run the standalone filtering checks from the repository root:

```bash
swiftc ios/Sources/MoodSync/Models.swift ios/Checks/FilterChecks.swift -o /tmp/moodsync-filter-checks
/tmp/moodsync-filter-checks
```

The portable contract is documented in [FORMAT.md](FORMAT.md).

## Notes

- Mood analysis uses Essentia DEAM for valence/arousal and Discogs400 for genres/styles. Bass emphasis, spectral brightness, dynamic range, and transient punch are calculated directly from the audio excerpts already used by the models. No text lookup or caption request is made during analysis.
- A local Whisper model checks three full song excerpts for vocal language. Songs whose audio has no confident language result remain undetermined. Existing libraries can fill missing languages without rerunning mood and genre analysis: `server/.venv/bin/python server/backfill_languages.py` from the repository root. Sync the iPhone after the pass finishes.
- New sound filters can be populated quickly for an existing library without rerunning the larger models: `server/.venv/bin/python server/backfill_sound.py` from the repository root. It samples the local audio files and refreshes the manifest as it proceeds.
- Mood and sound sliders use library-relative percentiles when at least ten songs have that feature, making narrow model outputs such as danceability easier to explore. Original model scores remain in each song's metadata as `raw_*`. Values are relative rankings, not absolute probabilities, and may shift as your library changes. Mood estimates can still differ from a listener's interpretation.
- Install the separate Python 3.12 ML environment from `server/requirements-ml.txt` and run `server/setup_models.py` before acquiring songs. Restart the server after updating the plugin or models. The dashboard's **Start reanalysis** button recalculates mood, sound, genre, and language data for every ready song; model upgrades also schedule unfinished songs automatically. The dashboard shows progress, elapsed time, an estimated time remaining, stages, and failures, with Pause and Resume controls. Sync the iPhone after analysis to see updated tags and positions.
- Provider metadata is optional. Artist, language, album, and release date remain unknown when a manual import or plugin cannot supply them.
- Automatic playlist polling runs in the server process. For an always-on library, run the server as a user service and keep its library directory on persistent storage.
