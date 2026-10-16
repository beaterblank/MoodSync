from __future__ import annotations

import json, os, shutil, subprocess, threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .analysis import audio_features
from .language import canonical_language

from .database import db
from .calibration import calibrate

ROOT=Path(__file__).resolve().parents[1]
LIBRARY=Path(os.getenv("MOODSYNC_LIBRARY",ROOT/"library")).resolve();TRACKS=LIBRARY/"tracks";STAGING=LIBRARY/".staging"
metadata_lock=threading.RLock()
LEGACY_LYRIC_FIELDS={"lyrics_source","lyrics_language","lyrics_lookup_status","lyric_sentiment","lyric_confidence"}
def now()->str:return datetime.now(timezone.utc).isoformat()

def safe_staged_file(staging:Path,value:str|Path)->Path:
    path=(staging/value).resolve() if not Path(value).is_absolute() else Path(value).resolve()
    if staging.resolve() not in path.parents:raise ValueError("Plugin returned a file outside its staging directory")
    if not path.is_file():raise ValueError(f"Plugin output is missing: {path.name}")
    return path

def ingest_staged(track_id:str,provider:str,external_id:str,staging:Path,result:dict[str,Any],progress:Callable[[float,str],None],entry:dict|None=None)->None:
    """Validate untrusted plugin output; core alone installs and analyses it."""
    source=safe_staged_file(staging,result.pop("audio"));metadata=result.get("metadata",{})
    if not isinstance(metadata,dict):raise ValueError("Plugin metadata must be an object")
    folder=TRACKS/track_id;temporary=TRACKS/f".{track_id}-{threading.get_ident()}"
    if temporary.exists():shutil.rmtree(temporary)
    temporary.mkdir(parents=True,exist_ok=True);audio=temporary/"audio.m4a"
    progress(.55,"Transcoding")
    subprocess.run(["ffmpeg","-v","error","-y","-i",str(source),"-vn","-c:a","aac","-b:a","256k",str(audio)],capture_output=True,text=True,check=True)
    artwork_value=result.get("artwork");cover=temporary/"cover.jpg"
    if artwork_value:
        artwork=safe_staged_file(staging,artwork_value)
        subprocess.run(["ffmpeg","-v","error","-y","-i",str(artwork),"-frames:v","1",str(cover)],capture_output=True,text=True,check=True)
    has_cover=cover.exists()
    progress(.73,"Analyzing audio with the mood model")
    features=audio_features(audio);date=str(metadata.get("release_date") or "") or None
    year=metadata.get("release_year")
    if not year and date and date[:4].isdigit():year=int(date[:4])
    duration=metadata.get("duration")
    if duration is None:
        probe=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",str(audio)],capture_output=True,text=True,check=True);duration=float(probe.stdout.strip())
    progress(.97,"Saving music metadata")
    language=canonical_language(features.get("audio_language")) or canonical_language(metadata.get("language"))
    canonical={"id":track_id,"title":str(metadata.get("title") or external_id),"artist":str(metadata.get("artist") or "Unknown artist"),"album":str(metadata.get("album") or ""),"language":language,"release_date":date,"release_year":year,"duration":duration,"thumbnail":metadata.get("thumbnail"),**features,"status":"ready","audio":"audio.m4a","artwork":"cover.jpg" if has_cover else None,"provider":provider,"external_id":external_id}
    (temporary/"metadata.json").write_text(json.dumps(canonical,indent=2,ensure_ascii=False),encoding="utf-8")
    backup=TRACKS/f".{track_id}-old"
    if backup.exists():shutil.rmtree(backup)
    if folder.exists():folder.replace(backup)
    temporary.replace(folder)
    if backup.exists():shutil.rmtree(backup)
    with db() as c:c.execute("""UPDATE tracks SET title=?,artist=?,album=?,language=?,tags=?,release_date=?,release_year=?,duration=?,thumbnail=?,valence=?,arousal=?,tempo=?,energy=?,acousticness=?,status='ready',progress=1,error=NULL,analysis_status='complete',analysis_progress=1,analysis_error=NULL,audio_path=?,artwork_path=?,metadata_path=?,provider=?,external_id=?,updated_at=? WHERE id=?""",(canonical["title"],canonical["artist"],canonical["album"],canonical["language"] or "unknown",json.dumps(canonical.get("tags",[])),date,year,duration,canonical["thumbnail"],features["valence"],features["arousal"],features["tempo"],features["energy"],features["acousticness"],str(folder/"audio.m4a"),str(folder/"cover.jpg") if has_cover else None,str(folder/"metadata.json"),provider,external_id,now(),track_id))
    write_manifest();progress(1,"Ready")

def write_manifest()->None:
    with metadata_lock:
        TRACKS.mkdir(parents=True,exist_ok=True);LIBRARY.mkdir(parents=True,exist_ok=True)
        with db() as c:rows=c.execute("SELECT metadata_path FROM tracks WHERE active=1 AND status='ready' ORDER BY artist,title").fetchall()
        originals=[]
        for row in rows:
            path=Path(row["metadata_path"] or "")
            if path.is_file():
                original=json.loads(path.read_text(encoding="utf-8"))
                normalized=dict(original)
                for key in LEGACY_LYRIC_FIELDS: normalized.pop(key,None)
                normalized["language"]=canonical_language(original.get("language"))
                originals.append((path,original,normalized))
        tracks=calibrate([item[2] for item in originals])
        updates=[]
        for (path,original,_),track in zip(originals,tracks):
            if track != original:
                temporary=path.with_suffix(".calibration-tmp")
                temporary.write_text(json.dumps(track,indent=2,ensure_ascii=False),encoding="utf-8")
                temporary.replace(path)
            updates.append((track.get("valence"),track.get("arousal"),track.get("energy"),
                            track.get("acousticness"),track.get("language") or "unknown",json.dumps(track.get("tags",[])),track["id"]))
        with db() as c:
            c.executemany("UPDATE tracks SET valence=?,arousal=?,energy=?,acousticness=?,language=?,tags=? WHERE id=?",updates)
        path=LIBRARY/"manifest.json";temporary=LIBRARY/f"manifest.tmp-{threading.get_ident()}";temporary.write_text(json.dumps({"version":1,"generated_at":now(),"tracks":tracks},indent=2,ensure_ascii=False),encoding="utf-8");temporary.replace(path)

def remove_track_files(track_id:str)->None:
    folder=TRACKS/track_id
    if folder.exists():shutil.rmtree(folder)
