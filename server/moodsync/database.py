from __future__ import annotations

import os, sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.getenv("MOODSYNC_DB", ROOT / "data" / "moodsync.sqlite3"))

@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA journal_mode=WAL")
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()

def init_db() -> None:
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS sources(
          id INTEGER PRIMARY KEY, url TEXT UNIQUE NOT NULL, title TEXT NOT NULL DEFAULT '',
          provider TEXT NOT NULL DEFAULT 'legacy', config TEXT NOT NULL DEFAULT '{}',
          kind TEXT NOT NULL DEFAULT 'playlist', enabled INTEGER NOT NULL DEFAULT 1,
          delete_removed INTEGER NOT NULL DEFAULT 1, last_synced_at TEXT, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tracks(
          id TEXT PRIMARY KEY, title TEXT NOT NULL DEFAULT '', artist TEXT NOT NULL DEFAULT '',
          provider TEXT NOT NULL DEFAULT 'manual', external_id TEXT,
          acquisition_data TEXT NOT NULL DEFAULT '{}',
          album TEXT NOT NULL DEFAULT '', language TEXT NOT NULL DEFAULT 'unknown',
          release_date TEXT, release_year INTEGER, duration REAL, thumbnail TEXT,
          valence REAL, arousal REAL, tempo REAL, energy REAL, acousticness REAL,
          status TEXT NOT NULL DEFAULT 'queued', progress REAL NOT NULL DEFAULT 0,
          error TEXT, audio_path TEXT, artwork_path TEXT, metadata_path TEXT,
          active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS source_tracks(
          source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
          track_id TEXT NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
          position INTEGER NOT NULL DEFAULT 0, present INTEGER NOT NULL DEFAULT 1,
          PRIMARY KEY(source_id,track_id)
        );
        CREATE TABLE IF NOT EXISTS jobs(
          id INTEGER PRIMARY KEY, track_id TEXT REFERENCES tracks(id) ON DELETE CASCADE,
          kind TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued', message TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_tracks_status ON tracks(status);
        CREATE INDEX IF NOT EXISTS idx_source_tracks_source ON source_tracks(source_id);
        """)
        # Forward-only, non-destructive migrations for databases made by earlier previews.
        source_columns={row[1] for row in c.execute("PRAGMA table_info(sources)")}
        track_columns={row[1] for row in c.execute("PRAGMA table_info(tracks)")}
        if "provider" not in source_columns: c.execute("ALTER TABLE sources ADD COLUMN provider TEXT NOT NULL DEFAULT 'legacy'")
        if "config" not in source_columns: c.execute("ALTER TABLE sources ADD COLUMN config TEXT NOT NULL DEFAULT '{}'")
        if "provider" not in track_columns: c.execute("ALTER TABLE tracks ADD COLUMN provider TEXT NOT NULL DEFAULT 'manual'")
        if "external_id" not in track_columns: c.execute("ALTER TABLE tracks ADD COLUMN external_id TEXT")
        if "acquisition_data" not in track_columns: c.execute("ALTER TABLE tracks ADD COLUMN acquisition_data TEXT NOT NULL DEFAULT '{}'")
        if "analysis_status" not in track_columns: c.execute("ALTER TABLE tracks ADD COLUMN analysis_status TEXT NOT NULL DEFAULT 'pending'")
        if "analysis_progress" not in track_columns: c.execute("ALTER TABLE tracks ADD COLUMN analysis_progress REAL NOT NULL DEFAULT 0")
        if "analysis_error" not in track_columns: c.execute("ALTER TABLE tracks ADD COLUMN analysis_error TEXT")
        if "tags" not in track_columns: c.execute("ALTER TABLE tracks ADD COLUMN tags TEXT NOT NULL DEFAULT '[]'")
        if "lyrics_status" in track_columns: c.execute("ALTER TABLE tracks DROP COLUMN lyrics_status")
        c.execute("UPDATE sources SET config=json_object('location',url) WHERE config='{}' AND url LIKE 'http%'")
