"""Fail-closed configuration check for the dedicated private VPS service."""
import os
import re
from pathlib import Path

ROOT=Path("/var/lib/cyberbot")
PATHS={"CYBERBOT_DB":"var/paper.sqlite3","CYBERBOT_LEARNING_DB":"var/learning.sqlite3","CYBERBOT_WORKER_DB":"var/worker.sqlite3"}
DISABLED=("CYBERBOT_TAILSCALE_WRITE","CYBERBOT_SOLANA_READ_ENABLED","CYBERBOT_LOCAL_LLM_ENABLED","CYBERBOT_CHRONOS_ENABLED","CYBERBOT_FX_PROVIDER_ENABLED")

def validate(env,root=ROOT):
    errors=[]
    host=env.get("CYBERBOT_TAILSCALE_HOST","")
    login=env.get("CYBERBOT_TAILSCALE_LOGIN","")
    if env.get("CYBERBOT_TAILSCALE_ENABLED")!="1":errors.append("Özel Tailscale erişimi etkin olmalı.")
    if not re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+\.ts\.net",host) or host.startswith("replace-me."):
        errors.append("Doğrulanmış MagicDNS adı gerekli.")
    if not login or login.startswith("replace-me") or login.endswith(".invalid") or any(c.isspace() for c in login):
        errors.append("Doğrulanmış Tailscale kullanıcı adı gerekli.")
    if env.get("CYBERBOT_TAILSCALE_PORT")!="8443":errors.append("Bu servis için özel HTTPS portu 8443 olmalı.")
    for k in DISABLED:
        if env.get(k,"0")!="0":errors.append(k+" kapalı olmalı.")
    for k,v in PATHS.items():
        raw=env.get(k,"")
        expected=root/v
        if raw!=str(expected) or Path(raw).resolve()!=expected.absolute():
            errors.append(k+" ayrılmış Cyberbot dizininde olmalı.")
    # Optional input files are local only and cannot point at an unrelated user's data.
    for k in ("CYBERBOT_EBBOT_DB","CYBERBOT_FX_FILE","CYBERBOT_COVERAGE_REPORT","CYBERBOT_NASDAQ_5M_REPORT","CYBERBOT_BIST_XETRA_5M_REPORT"):
        if env.get(k):
            p=Path(env[k])
            if not p.is_absolute() or not p.resolve().is_relative_to(root/"inputs"):
                errors.append(k+" /var/lib/cyberbot/inputs altında olmalı.")
    if env.get("CYBERBOT_PILOT_DB"):errors.append("Özel pilot DB yolu bu dağıtımda desteklenmiyor.")
    return errors

def main():
    errors=validate(os.environ)
    if errors:
        for error in errors:print(error)
        raise SystemExit(1)
    from cyberbot.db_paths import checked
    checked()
    print("Cyberbot özel salt okunur erişim yapılandırması: PASS")

if __name__=="__main__":main()
