from __future__ import annotations

import importlib.util,json,os,re,shutil,subprocess,tempfile
from abc import ABC,abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any,Callable

ROOT=Path(__file__).resolve().parents[1];MANAGED=ROOT/"plugin-repos";API_VERSION=1

@dataclass
class SourceSnapshot:
    title:str
    entries:list[dict[str,Any]]

class AcquisitionPlugin(ABC):
    """Required interface for trusted acquisition plugins loaded by MoodSync."""
    @abstractmethod
    def inspect(self,config:dict[str,Any])->SourceSnapshot:
        """Return the source's current items; every entry needs a stable external_id."""
    @abstractmethod
    def acquire(self,entry:dict[str,Any],destination:Path,progress:Callable[[float,str],None])->dict[str,Any]:
        """Place source media in destination and return relative paths plus metadata."""

@dataclass
class LoadedPlugin:
    id:str;name:str;description:str;fields:list[dict[str,Any]];plugin:AcquisitionPlugin;path:Path;managed:bool
    def public(self)->dict[str,Any]:return {"id":self.id,"name":self.name,"description":self.description,"fields":self.fields,"managed":self.managed,"path":str(self.path)}

def git(args:list[str],cwd:Path|None=None)->str:
    result=subprocess.run(["git",*args],cwd=cwd,capture_output=True,text=True,timeout=120)
    if result.returncode:raise RuntimeError((result.stderr or result.stdout).strip()[-1000:])
    return result.stdout.strip()

class PluginRegistry:
    def __init__(self):self.loaded:dict[str,LoadedPlugin]={};self.errors:list[dict[str,str]]=[];self.reload()
    def roots(self)->list[Path]:
        configured=[Path(p).expanduser().resolve() for p in os.getenv("MOODSYNC_PLUGIN_DIRS","").split(os.pathsep) if p]
        return [MANAGED,*configured]
    def manifests(self):
        for root in self.roots():
            if not root.is_dir():continue
            yield from root.glob("*/plugin.json")
    def read_manifest(self,path:Path)->dict[str,Any]:
        manifest=json.loads(path.read_text(encoding="utf-8"));plugin_id=manifest["id"]
        if manifest.get("api_version")!=API_VERSION:raise ValueError(f"plugin api_version must be {API_VERSION}")
        if not re.fullmatch(r"[a-z][a-z0-9_-]{1,40}",plugin_id):raise ValueError("invalid plugin id")
        if not isinstance(manifest.get("fields",[]),list):raise ValueError("fields must be a list")
        return manifest
    def reload(self)->None:
        self.loaded={};self.errors=[]
        for manifest_path in self.manifests():
            try:
                manifest=self.read_manifest(manifest_path);plugin_id=manifest["id"];folder=manifest_path.parent.resolve();module_path=(folder/manifest.get("module","plugin.py")).resolve()
                if folder not in module_path.parents or not module_path.is_file():raise ValueError("plugin module must be a file inside its repository")
                spec=importlib.util.spec_from_file_location(f"moodsync_addon_{plugin_id}",module_path)
                if not spec or not spec.loader:raise ImportError("could not create module spec")
                module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);plugin_class=getattr(module,"Plugin",None)
                if not isinstance(plugin_class,type) or not issubclass(plugin_class,AcquisitionPlugin):raise TypeError("Plugin must subclass moodsync.plugins.AcquisitionPlugin")
                instance=plugin_class();self.loaded[plugin_id]=LoadedPlugin(plugin_id,manifest["name"],manifest.get("description",""),manifest.get("fields",[]),instance,folder,MANAGED.resolve() in folder.parents)
            except Exception as error:self.errors.append({"path":str(manifest_path),"error":str(error)})
    def get(self,plugin_id:str)->LoadedPlugin:
        try:return self.loaded[plugin_id]
        except KeyError:raise KeyError(f"Acquisition plugin '{plugin_id}' is not installed or failed to load")
    def install(self,repository:str,ref:str|None=None)->LoadedPlugin:
        if not repository.strip():raise ValueError("Repository is required")
        MANAGED.mkdir(parents=True,exist_ok=True)
        temporary=Path(tempfile.mkdtemp(prefix="plugin-install-",dir=MANAGED))
        try:
            args=["clone","--depth","1"]
            if ref:args += ["--branch",ref]
            args += [repository, str(temporary/"repo")];git(args)
            manifest_path=temporary/"repo"/"plugin.json"
            if not manifest_path.is_file():raise ValueError("Repository must contain plugin.json at its root")
            manifest=self.read_manifest(manifest_path);destination=MANAGED/manifest["id"]
            if destination.exists():raise FileExistsError(f"Plugin '{manifest['id']}' is already installed")
            (temporary/"repo").replace(destination);self.reload()
            if manifest["id"] not in self.loaded:
                failure=next((e["error"] for e in self.errors if str(destination) in e["path"]),"plugin failed to load");shutil.rmtree(destination,ignore_errors=True);self.reload();raise RuntimeError(failure)
            return self.loaded[manifest["id"]]
        finally:shutil.rmtree(temporary,ignore_errors=True)
    def update(self,plugin_id:str)->LoadedPlugin:
        loaded=self.get(plugin_id)
        if not loaded.managed or not (loaded.path/".git").is_dir():raise ValueError("Only plugins installed from the UI can be updated")
        git(["pull","--ff-only"],loaded.path);self.reload();return self.get(plugin_id)
    def remove(self,plugin_id:str)->None:
        loaded=self.get(plugin_id)
        if not loaded.managed:raise ValueError("Plugins from external configured directories cannot be removed here")
        target=loaded.path.resolve()
        if MANAGED.resolve() not in target.parents:raise ValueError("Invalid managed plugin path")
        shutil.rmtree(target);self.reload()

registry=PluginRegistry()
