from __future__ import annotations

import hashlib,json,os,shutil,threading,uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from fastapi import FastAPI,File,Form,Header,HTTPException,UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field

from .database import db,init_db
from .errors import describe_error
from .discovery import advertisement
from . import reanalyze
from .library import LIBRARY,STAGING,TRACKS,ingest_staged,now,remove_track_files,write_manifest
from .plugins import registry

ROOT=Path(__file__).resolve().parents[1];STATIC=ROOT/"static";TOKEN=os.getenv("MOODSYNC_SYNC_TOKEN","")
app=FastAPI(title="MoodSync",version="2.0.0");app.mount("/static",StaticFiles(directory=STATIC),name="static")
WORKERS=max(1,int(os.getenv("MOODSYNC_WORKERS",str(min(12,max(4,os.cpu_count() or 4))))))
pool=ThreadPoolExecutor(max_workers=WORKERS,thread_name_prefix="moodsync");stop_scheduler=threading.Event()

class SourceIn(BaseModel):
    plugin:str=Field(min_length=2,max_length=50)
    config:dict[str,Any]
    delete_removed:bool=True

class PluginInstall(BaseModel):
    repository:str=Field(min_length=1,max_length=1000)
    ref:str|None=Field(default=None,max_length=200)

def require_token(value:str|None):
    if TOKEN and value!=f"Bearer {TOKEN}":raise HTTPException(401,"Invalid sync token")

@app.get("/api/device/health")
def device_health():
    return {"service":"moodsync","version":1,"name":os.getenv("MOODSYNC_SERVER_NAME","My music library"),"requires_token":bool(TOKEN)}

@app.get("/api/analysis/status")
def analysis_status():return reanalyze.status()

@app.post("/api/analysis/rebuild",status_code=202)
def analysis_rebuild(force:bool=False):return reanalyze.start(force=force)

@app.post("/api/analysis/pause")
def analysis_pause():return reanalyze.pause()

def global_id(provider:str,external_id:str)->str:
    clean="".join(c for c in external_id if c.isalnum() or c in "_-")[:80]
    return f"{provider}__{clean or hashlib.sha256(external_id.encode()).hexdigest()[:24]}"
def update_progress(track_id:str,value:float,message:str):
    status="ready" if value>=1 else ("analysing" if value>=.7 else "acquiring")
    with db() as c:c.execute("UPDATE tracks SET status=?,progress=?,error=NULL,updated_at=? WHERE id=?",(status,value,now(),track_id));c.execute("UPDATE jobs SET message=? WHERE track_id=? AND status='running'",(message,track_id))

def run_acquisition(track_id:str,job_id:int):
    with db() as c:
        row=c.execute("SELECT provider,external_id,acquisition_data FROM tracks WHERE id=?",(track_id,)).fetchone();c.execute("UPDATE jobs SET status='running',started_at=? WHERE id=?",(now(),job_id))
    staging=STAGING/f"{job_id}-{uuid.uuid4().hex}"
    try:
        staging.mkdir(parents=True,exist_ok=False);plugin=registry.get(row["provider"]).plugin;entry=json.loads(row["acquisition_data"]);result=plugin.acquire(entry,staging,lambda p,m:update_progress(track_id,p,m));ingest_staged(track_id,row["provider"],row["external_id"],staging,result,lambda p,m:update_progress(track_id,p,m),entry=entry)
        with db() as c:c.execute("UPDATE jobs SET status='done',message='Ready',finished_at=? WHERE id=?",(now(),job_id))
    except Exception as error:
        with db() as c:c.execute("UPDATE tracks SET status='failed',error=?,updated_at=? WHERE id=?",(describe_error(error),now(),track_id));c.execute("UPDATE jobs SET status='failed',message=?,finished_at=? WHERE id=?",(describe_error(error),now(),job_id))
    finally:shutil.rmtree(staging,ignore_errors=True)

def run_manual(track_id:str,job_id:int,staging:Path,metadata:dict[str,Any]):
    with db() as c:c.execute("UPDATE jobs SET status='running',started_at=? WHERE id=?",(now(),job_id))
    try:
        files=json.loads((staging/"job.json").read_text());ingest_staged(track_id,"manual",track_id,staging,{"audio":files["audio"],"artwork":files.get("cover"),"metadata":metadata},lambda p,m:update_progress(track_id,p,m))
        with db() as c:c.execute("UPDATE jobs SET status='done',message='Ready',finished_at=? WHERE id=?",(now(),job_id))
    except Exception as error:
        with db() as c:c.execute("UPDATE tracks SET status='failed',error=?,updated_at=? WHERE id=?",(describe_error(error),now(),track_id));c.execute("UPDATE jobs SET status='failed',message=?,finished_at=? WHERE id=?",(describe_error(error),now(),job_id))
    finally:shutil.rmtree(staging,ignore_errors=True)

def queue_track(provider:str,entry:dict[str,Any]):
    external_id=str(entry["external_id"]);track_id=global_id(provider,external_id)
    with db() as c:
        c.execute("""INSERT INTO tracks(id,title,artist,provider,external_id,acquisition_data,status,created_at,updated_at) VALUES(?,?,?,?,?,?,'queued',?,?) ON CONFLICT(id) DO UPDATE SET active=1,provider=excluded.provider,external_id=excluded.external_id,acquisition_data=excluded.acquisition_data,status=CASE WHEN tracks.active=0 THEN 'queued' ELSE tracks.status END,progress=CASE WHEN tracks.active=0 THEN 0 ELSE tracks.progress END,updated_at=excluded.updated_at""",(track_id,entry.get("title") or external_id,"",provider,external_id,json.dumps(entry),now(),now()))
        existing=c.execute("SELECT id FROM jobs WHERE track_id=? AND status IN ('queued','running')",(track_id,)).fetchone();status=c.execute("SELECT status FROM tracks WHERE id=?",(track_id,)).fetchone()["status"]
        if existing or status=="ready":return track_id
        job_id=c.execute("INSERT INTO jobs(track_id,kind,status,created_at) VALUES(?,'acquire','queued',?) RETURNING id",(track_id,now())).fetchone()["id"]
    pool.submit(run_acquisition,track_id,job_id);return track_id

def sync_source(source_id:int):
    with db() as c:source=c.execute("SELECT * FROM sources WHERE id=?",(source_id,)).fetchone()
    if not source:raise HTTPException(404,"Source not found")
    try:plugin=registry.get(source["provider"])
    except KeyError as error:raise HTTPException(409,str(error))
    snapshot=plugin.plugin.inspect(json.loads(source["config"]));entries=snapshot.entries;track_entries={global_id(plugin.id,str(e["external_id"])):e for e in entries};incoming=set(track_entries)
    with db() as c:
        previous={r["track_id"] for r in c.execute("SELECT track_id FROM source_tracks WHERE source_id=? AND present=1",(source_id,))};c.execute("UPDATE sources SET title=?,last_synced_at=? WHERE id=?",(snapshot.title,now(),source_id));c.execute("UPDATE source_tracks SET present=0 WHERE source_id=?",(source_id,))
    for position,(track_id,entry) in enumerate(track_entries.items()):
        queue_track(plugin.id,entry)
        with db() as c:c.execute("INSERT INTO source_tracks(source_id,track_id,position,present) VALUES(?,?,?,1) ON CONFLICT(source_id,track_id) DO UPDATE SET position=excluded.position,present=1",(source_id,track_id,position))
    removed=previous-incoming
    if source["delete_removed"]:
        with db() as c:
            for track_id in removed:
                if not c.execute("SELECT 1 FROM source_tracks WHERE track_id=? AND present=1 LIMIT 1",(track_id,)).fetchone():c.execute("UPDATE tracks SET active=0,updated_at=? WHERE id=?",(now(),track_id));remove_track_files(track_id)
    write_manifest();return {"title":snapshot.title,"found":len(entries),"added":len(incoming-previous),"removed":len(removed)}

def scheduler():
    minutes=max(1,int(os.getenv("MOODSYNC_SYNC_INTERVAL_MINUTES","30")))
    while not stop_scheduler.wait(minutes*60):
        with db() as c:ids=[r["id"] for r in c.execute("SELECT id FROM sources WHERE enabled=1")]
        for source_id in ids:
            try:sync_source(source_id)
            except Exception:pass

@app.on_event("startup")
async def startup():
    await advertisement.start()
    stop_scheduler.clear();init_db();TRACKS.mkdir(parents=True,exist_ok=True);STAGING.mkdir(parents=True,exist_ok=True);registry.reload()
    with db() as c:
        # Repair the v2.0 progress-callback bug: these jobs fully completed and
        # wrote canonical metadata, but their final callback relabeled them.
        c.execute("""UPDATE tracks SET status='ready',progress=1 WHERE status='analysing' AND metadata_path IS NOT NULL AND EXISTS(SELECT 1 FROM jobs WHERE jobs.track_id=tracks.id AND jobs.status='done')""")
        c.execute("UPDATE jobs SET status='failed',message='Interrupted by restart',finished_at=? WHERE status IN ('queued','running')",(now(),))
        pending=c.execute("SELECT provider,acquisition_data FROM tracks WHERE active=1 AND status IN ('queued','acquiring','analysing') AND provider!='manual'").fetchall();c.execute("UPDATE tracks SET status='queued',progress=0 WHERE status IN ('acquiring','analysing')")
    for row in pending:queue_track(row["provider"],json.loads(row["acquisition_data"]))
    write_manifest();threading.Thread(target=scheduler,name="source-sync",daemon=True).start();reanalyze.restore()

@app.on_event("shutdown")
async def shutdown():await advertisement.stop();stop_scheduler.set();pool.shutdown(wait=False,cancel_futures=True)

@app.get("/")
def home():return FileResponse(STATIC/"index.html")
@app.get("/api/plugins")
def plugins():return {"plugins":[p.public() for p in registry.loaded.values()],"errors":registry.errors}
@app.post("/api/plugins/reload")
def reload_plugins():registry.reload();return plugins()
@app.post("/api/plugins/install",status_code=201)
def install_plugin(payload:PluginInstall):
    try:return registry.install(payload.repository,payload.ref).public()
    except Exception as error:raise HTTPException(400,str(error))
@app.post("/api/plugins/{plugin_id}/update")
def update_plugin(plugin_id:str):
    try:return registry.update(plugin_id).public()
    except (KeyError,ValueError,RuntimeError) as error:raise HTTPException(400,str(error))
@app.delete("/api/plugins/{plugin_id}")
def remove_plugin(plugin_id:str):
    with db() as c:used=c.execute("SELECT 1 FROM sources WHERE provider=? LIMIT 1",(plugin_id,)).fetchone()
    if used:raise HTTPException(409,"Remove this plugin's sources before uninstalling it")
    try:registry.remove(plugin_id);return {"ok":True}
    except (KeyError,ValueError) as error:raise HTTPException(400,str(error))
@app.get("/api/status")
def status():
    with db() as c:counts={r["status"]:r["count"] for r in c.execute("SELECT status,COUNT(*) count FROM tracks WHERE active=1 GROUP BY status")};sources=c.execute("SELECT COUNT(*) n FROM sources WHERE enabled=1").fetchone()["n"]
    return {"tracks":counts,"sources":sources,"library":str(LIBRARY),"plugins":len(registry.loaded),"workers":WORKERS}
@app.get("/api/sources")
def sources():
    with db() as c:rows=c.execute("SELECT s.*,COUNT(st.track_id) track_count FROM sources s LEFT JOIN source_tracks st ON st.source_id=s.id AND st.present=1 GROUP BY s.id ORDER BY s.created_at DESC").fetchall()
    return [{**dict(r),"config":json.loads(r["config"])} for r in rows]
@app.post("/api/sources",status_code=201)
def add_source(payload:SourceIn):
    try:plugin=registry.get(payload.plugin)
    except KeyError as error:raise HTTPException(400,str(error))
    location=f"{payload.plugin}:{json.dumps(payload.config,sort_keys=True,separators=(',',':'))}"
    try:
        with db() as c:source_id=c.execute("INSERT INTO sources(url,provider,config,delete_removed,created_at) VALUES(?,?,?,?,?) RETURNING id",(location,payload.plugin,json.dumps(payload.config),int(payload.delete_removed),now())).fetchone()["id"]
    except Exception as error:
        if "UNIQUE" in str(error):raise HTTPException(409,"This plugin source already exists")
        raise
    return {"id":source_id,**sync_source(source_id)}
@app.post("/api/sources/{source_id}/sync")
def resync(source_id:int):return sync_source(source_id)
@app.delete("/api/sources/{source_id}")
def delete_source(source_id:int):
    with db() as c:c.execute("DELETE FROM sources WHERE id=?",(source_id,))
    return {"ok":True}

@app.post("/api/import",status_code=202)
async def manual_import(audio:UploadFile=File(...),title:str=Form(""),artist:str=Form("Unknown artist"),language:str=Form("unknown"),release_year:int|None=Form(None),cover:UploadFile|None=File(None)):
    manual_id=f"manual__{uuid.uuid4().hex}";staging=STAGING/manual_id;staging.mkdir(parents=True);audio_suffix=Path(audio.filename or ".audio").suffix or ".audio";audio_name="source"+audio_suffix
    with (staging/audio_name).open("wb") as target:
        while chunk:=await audio.read(1024*1024):target.write(chunk)
    cover_name=None
    if cover:
        cover_suffix=Path(cover.filename or ".jpg").suffix or ".jpg";cover_name="cover"+cover_suffix
        with (staging/cover_name).open("wb") as target:
            while chunk:=await cover.read(1024*1024):target.write(chunk)
    (staging/"job.json").write_text(json.dumps({"audio":audio_name,"cover":cover_name}))
    metadata={"title":title or Path(audio.filename or "Imported track").stem,"artist":artist,"language":language,"release_year":release_year}
    with db() as c:c.execute("INSERT INTO tracks(id,title,artist,provider,external_id,status,created_at,updated_at) VALUES(?,?,?,'manual',?,'queued',?,?)",(manual_id,metadata["title"],artist,manual_id,now(),now()));job_id=c.execute("INSERT INTO jobs(track_id,kind,status,created_at) VALUES(?,'manual-import','queued',?) RETURNING id",(manual_id,now())).fetchone()["id"]
    pool.submit(run_manual,manual_id,job_id,staging,metadata);return {"id":manual_id,"status":"queued"}

@app.get("/api/tracks")
def tracks(status:str="",q:str=""):
    where=["active=1"];params=[]
    if status:where.append("status=?");params.append(status)
    if q:where.append("(title LIKE ? OR artist LIKE ?)");params += [f"%{q}%",f"%{q}%"]
    with db() as c:rows=c.execute(f"SELECT * FROM tracks WHERE {' AND '.join(where)} ORDER BY updated_at DESC",params).fetchall()
    return [{**dict(r), "tags": json.loads(r["tags"] or "[]")} for r in rows]
@app.post("/api/tracks/{track_id}/retry")
def retry(track_id:str):
    with db() as c:row=c.execute("SELECT provider,acquisition_data FROM tracks WHERE id=?",(track_id,)).fetchone();c.execute("UPDATE tracks SET status='queued',progress=0,error=NULL WHERE id=?",(track_id,))
    if not row:raise HTTPException(404,"Track not found")
    if row["provider"]=="manual":raise HTTPException(409,"Re-import the local file to retry a manual import")
    queue_track(row["provider"],json.loads(row["acquisition_data"]));return {"ok":True}
@app.post("/api/tracks/retry-failed")
def retry_failed():
    with db() as c:rows=c.execute("SELECT id,provider,acquisition_data FROM tracks WHERE active=1 AND status='failed' AND provider!='manual'").fetchall()
    queued=0
    for row in rows:
        with db() as c:c.execute("UPDATE tracks SET status='queued',progress=0,error=NULL,updated_at=? WHERE id=?",(now(),row["id"]))
        queue_track(row["provider"],json.loads(row["acquisition_data"]));queued+=1
    return {"queued":queued}
@app.delete("/api/tracks/{track_id}")
def delete_track(track_id:str):
    with db() as c:c.execute("DELETE FROM tracks WHERE id=?",(track_id,))
    remove_track_files(track_id);write_manifest();return {"ok":True}

@app.get("/api/device/manifest")
def device_manifest(authorization:str|None=Header(default=None)):require_token(authorization);write_manifest();return FileResponse(LIBRARY/"manifest.json",media_type="application/json")
def media_file(track_id:str,name:str,authorization:str|None):
    require_token(authorization)
    if name not in {"audio.m4a","cover.jpg","metadata.json"}:raise HTTPException(404)
    path=TRACKS/track_id/name
    if not path.is_file():raise HTTPException(404,"Media file not found")
    return FileResponse(path)
@app.get("/api/device/tracks/{track_id}/audio.m4a")
def device_audio(track_id:str,authorization:str|None=Header(default=None)):return media_file(track_id,"audio.m4a",authorization)
@app.get("/api/device/tracks/{track_id}/cover.jpg")
def device_cover(track_id:str,authorization:str|None=Header(default=None)):return media_file(track_id,"cover.jpg",authorization)
@app.get("/api/device/tracks/{track_id}/metadata.json")
def device_metadata(track_id:str,authorization:str|None=Header(default=None)):return media_file(track_id,"metadata.json",authorization)
