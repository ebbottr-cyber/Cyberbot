"""Recover a Cyberbot backup into a new isolated directory, never over active files."""
import hashlib,json,shutil,tempfile,re
from datetime import datetime,timezone
from pathlib import Path
from .operations import inspect_db,required
from .db_paths import checked,same,resolved

NAMES={"paper","learning","paper_bist","paper_nasdaq","paper_xetra","paper_solana","futures"}
MAX_MANIFEST=65536
MAX_FILE_BYTES=20*1024**3

def digest(path):
    with path.open("rb") as stream:return hashlib.file_digest(stream,"sha256").hexdigest()

def manifest_entries(folder):
    path=folder/"manifest.json"
    if path.is_symlink() or not path.is_file():raise ValueError("Manifest bulunamadı.")
    with path.open("rb") as stream:raw=stream.read(MAX_MANIFEST+1)
    if len(raw)>MAX_MANIFEST:raise ValueError("Manifest çok büyük.")
    m=json.loads(raw)
    if not isinstance(m,dict) or m.get("scope")!="cyberbot_only" or not isinstance(m.get("files"),list) or not 1<=len(m["files"])<=len(NAMES):raise ValueError("Manifest kapsamı geçersiz.")
    entries={}
    for row in m["files"]:
        if not isinstance(row,dict):raise ValueError("Manifest kaydı geçersiz.")
        name=row.get("name");size=row.get("bytes");sha=row.get("sha256")
        if not isinstance(name,str) or not name.endswith(".sqlite3") or name[:-8] not in NAMES or name in entries or type(size) is not int or not 1<=size<=MAX_FILE_BYTES or not isinstance(sha,str) or not re.fullmatch(r"[0-9a-f]{64}",sha):
            raise ValueError("Manifest dosya kaydı geçersiz.")
        entries[name]=row
    skipped=m.get("skipped",[])
    if not isinstance(skipped,list) or any(not isinstance(x,str) or x not in NAMES or x+".sqlite3" in entries for x in skipped) or len(set(skipped))!=len(skipped):raise ValueError("Manifest atlama listesi geçersiz.")
    # No unexpected files, sidecar WAL or directory symlinks.
    if set(x.name for x in folder.iterdir())!=set(entries)|{"manifest.json"}:raise ValueError("Yedek klasörü beklenmeyen dosya içeriyor.")
    active=checked()
    for name,row in entries.items():
        src=folder/name
        if src.is_symlink() or not src.is_file() or any(same(src.resolve(),p) for p in active.values()) or src.stat().st_size!=row["bytes"] or digest(src)!=row["sha256"]:
            raise ValueError("Yedek dosyası doğrulanamadı: "+name)
    return m,entries

def recover(source,output):
    raw=Path(source).expanduser()
    if raw.is_symlink():raise ValueError("Yedek klasörü bağlantı olamaz.")
    folder=raw.resolve();root=resolved(output)
    if not folder.is_dir() or root==folder or folder in root.parents:raise ValueError("Ayrı kurtarma hedefi gerekli.")
    m,entries=manifest_entries(folder)
    root.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix=".recovery-",dir=root))
    try:
        restored=[]
        for name,row in entries.items():
            role=name[:-8]
            rel=Path("paper-markets")/name.removeprefix("paper_") if role.startswith("paper_") else Path("paper-markets/futures.sqlite3") if role=="futures" else Path(name)
            target=stage/rel;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(folder/name,target)
            if target.stat().st_size!=row["bytes"] or digest(target)!=row["sha256"] or inspect_db(target,required(role))!="ok" or digest(target)!=row["sha256"]:
                raise ValueError("Kurtarma bütünlük kontrolü başarısız: "+name)
            restored.append({"role":role,"path":rel.as_posix(),"bytes":row["bytes"],"sha256":row["sha256"]})
        report={"status":"verified_copy","source_created_at":m.get("created_at"),"restored":restored,"missing_roles":sorted(NAMES-{x["role"] for x in restored}),"active_files_modified":False,"activated":False,"worker_included":False,"cross_database_atomic_snapshot_verified":False,"real_orders":False}
        (stage/"recovery.json").write_text(json.dumps(report,indent=2,ensure_ascii=True),encoding="utf-8")
        target=root/("cyberbot-recovered-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
        if target.exists():raise ValueError("Kurtarma hedefi zaten var.")
        stage.rename(target)
        return target
    except BaseException:
        shutil.rmtree(stage,ignore_errors=True)
        raise
