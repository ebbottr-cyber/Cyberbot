"""Validate configured database separation before opening any app-owned writer."""
import os
from pathlib import Path

class PathCollision(ValueError):pass

def resolved(p):return Path(p).expanduser().resolve()
def same(a,b):
    return a==b or (a.exists() and b.exists() and a.samefile(b))

def layout(base=None):
    base=resolved(base or os.getenv("CYBERBOT_DB","var/paper.sqlite3"))
    root=base.parent/(base.stem+"-markets")
    paths={"paper":base,"learning":resolved(os.getenv("CYBERBOT_LEARNING_DB","var/learning.sqlite3")),"worker":resolved(os.getenv("CYBERBOT_WORKER_DB","var/worker.sqlite3"))}
    paths.update({"paper_"+m:resolved(root/(m+".sqlite3")) for m in ("bist","nasdaq","xetra","solana")})
    paths["futures"]=resolved(root/"futures.sqlite3")
    return paths

def pilot_path(base=None):
    p=layout(base)["paper"]
    return resolved(os.getenv("CYBERBOT_PILOT_DB") or p.parent/(p.stem+"-observed-pilot.sqlite3"))

def checked(base=None):
    paths=layout(base)
    protected=dict(paths)
    protected["observed_pilot"]=pilot_path(base)
    if os.getenv("CYBERBOT_EBBOT_DB"):protected["archive"]=resolved(os.environ["CYBERBOT_EBBOT_DB"])
    if os.getenv("CYBERBOT_FX_FILE"):protected["fx_input"]=resolved(os.environ["CYBERBOT_FX_FILE"])
    # Reserve adapter files even with adapter disabled; no DB may overwrite them.
    protected["fx_cache"]=resolved("var/fx-provider.json")
    protected["fx_quota"]=resolved("var/fx-provider-quota.sqlite3")
    for k,p in {**paths,"observed_pilot":protected["observed_pilot"]}.items():
        for other,q in protected.items():
            if k!=other and same(p,q):raise PathCollision("Veritabanı yolu çakışıyor: "+k+" / "+other)
    return paths
