"""Independent DexTerm MCP screener probe. No trading, no Cyberbot engine writes."""
import argparse
import json
import math
import os
from pathlib import Path
import queue
import shutil
import subprocess
import tempfile
import threading

from cyberbot.solana_pilot import address

PIN = "235a55e71f90ee5ba32d05ec11d90570ddd079c2"
MAX_LINE = 2 * 1024 * 1024
ALLOWED_FIELDS = ("priceUsd", "liquidityUsd", "mcap", "volH1", "holderCount",
                  "organicScore", "tokenAgeSec", "ageSec", "fetchedAt")

class ProbeFailure(ValueError):
    def __init__(self, reason, detail=None):
        super().__init__(reason)
        self.reason = reason
        self.detail = detail

def classify_stderr(data):
    # Only fixed diagnostic categories, never arbitrary stderr or local paths.
    markers = ("ERR_MODULE_NOT_FOUND", "MODULE_NOT_FOUND",
               "ERR_UNKNOWN_FILE_EXTENSION", "ERR_UNSUPPORTED_NODE_MODULES_TYPE_STRIPPING",
               "ERR_UNSUPPORTED_TYPESCRIPT_SYNTAX", "ERR_UNKNOWN_BUILTIN_MODULE",
               "ERR_PACKAGE_PATH_NOT_EXPORTED", "ERR_SQLITE_ERROR",
               "SQLITE_CANTOPEN", "ERR_INVALID_ARG_TYPE", "EACCES", "EPERM", "ENOENT",
               "SyntaxError", "TypeError", "ReferenceError")
    found = [m for m in markers if m.encode("ascii") in data]
    return found or (["unclassified_stderr"] if data else [])

def normalize(payload):
    if not isinstance(payload, dict) or payload.get("error"):
        raise ValueError("DexTerm tool error")
    rows = payload.get("rows")
    if not isinstance(rows, list) or len(rows) > 10:
        raise ValueError("Invalid screener rows")
    output = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or not address(row.get("mint")):
            continue
        mint = row["mint"]
        if mint in seen or mint == "So11111111111111111111111111111111111111112":
            continue
        seen.add(mint)
        values = {}
        for key in ALLOWED_FIELDS:
            value = row.get(key)
            if type(value) in (int, float) and math.isfinite(value) and value >= 0:
                values[key] = value
        output.append({"mint": mint, "reported": values, "security_verified": False})
    errors = payload.get("errors")
    if not isinstance(errors, (list, dict, type(None))):
        raise ValueError("Invalid source error field")
    return {"status": "diagnostic_partial" if errors or not output else "diagnostic_complete",
            "candidate_count": len(output), "candidates": output,
            "source_error_count": len(errors or []),
            "source": "dexterm_screener_query", "meme_classification_verified": False,
            "token_identity_verified": False, "security_verified": False,
            "depth_verified": False, "live_data_verified": False,
            "pilot_applied": False, "real_orders": False}

def isolated_env(home):
    # Do not forward API keys, wallets, analyst credentials, or DEXTERM_* settings.
    keep = ("PATH", "SystemRoot", "WINDIR", "COMSPEC", "PATHEXT", "SYSTEMDRIVE", "OS")
    env = {k: os.environ[k] for k in keep if k in os.environ}
    env.update({k: str(home) for k in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP", "TMPDIR")})
    env["DEXTERM_DB_PATH"] = ":memory:"
    return env

def probe(root, live=False):
    if os.getenv("CYBERBOT_PILOT_KILL_SWITCH") != "1":
        raise ProbeFailure("kill_switch_inactive")
    if live and os.getenv("CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED") != "1":
        raise ProbeFailure("data_permission_missing")
    root = Path(root).resolve(strict=True)
    if subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], timeout=10, text=True).strip() != PIN:
        raise ProbeFailure("revision_mismatch")
    if subprocess.check_output(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"], timeout=10, text=True).strip():
        raise ProbeFailure("tracked_files_modified")
    entry = root / "packages" / "mcp" / "bin" / "dexterm-mcp.mjs"
    node = shutil.which("node")
    if not entry.is_file() or not node:
        raise ProbeFailure("entry_or_node_missing")
    with tempfile.TemporaryDirectory(prefix="cyberbot-dexterm-") as home:
        proc = subprocess.Popen([node, str(entry)], cwd=home, env=isolated_env(home),
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        inbox = queue.Queue(maxsize=16)
        stderr_tail = bytearray()
        def stderr_reader():
            try:
                while True:
                    chunk = proc.stderr.read1(4096)
                    if not chunk:
                        return
                    stderr_tail.extend(chunk)
                    if len(stderr_tail) > 32768:
                        del stderr_tail[:-32768]
            except OSError:
                return
        stderr_worker = threading.Thread(target=stderr_reader, daemon=True)
        stderr_worker.start()
        def reader():
            try:
                while True:
                    line = proc.stdout.readline(MAX_LINE + 1)
                    if not line or len(line) > MAX_LINE:
                        inbox.put(None, timeout=1)
                        return
                    inbox.put(line, timeout=1)
            except (OSError, queue.Full):
                return
        worker = threading.Thread(target=reader, daemon=True)
        worker.start()
        def send(method, params, request_id=None):
            message = {"jsonrpc": "2.0", "method": method, "params": params}
            if request_id is not None:
                message["id"] = request_id
            proc.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
            proc.stdin.flush()
        def receive(request_id, timeout):
            try:
                line = inbox.get(timeout=timeout)
            except queue.Empty:
                raise ProbeFailure("mcp_response_timeout", {"request_id":request_id}) from None
            if line is None:
                raise ProbeFailure("mcp_stdout_closed_or_oversized", {"request_id":request_id})
            try:
                reply = json.loads(line)
            except (ValueError, UnicodeError):
                raise ProbeFailure("mcp_invalid_json", {"request_id":request_id}) from None
            if not isinstance(reply, dict) or reply.get("id") != request_id or "error" in reply:
                raise ProbeFailure("mcp_unexpected_response", {"request_id":request_id})
            result = reply.get("result")
            if not isinstance(result, dict):
                raise ProbeFailure("mcp_invalid_result", {"request_id":request_id})
            return result
        try:
            send("initialize", {"protocolVersion":"2025-06-18", "capabilities": {},
                                "clientInfo":{"name":"Cyberbot diagnostic", "version":"0.1"}}, 1)
            receive(1, 20)
            send("notifications/initialized", {})
            send("tools/list", {}, 2)
            tools = receive(2, 20).get("tools", [])
            if not any(isinstance(x, dict) and x.get("name") == "screener_query" for x in tools):
                raise ProbeFailure("screener_tool_missing")
            if not live:
                return {"status":"mcp_ready", "screener_available":True,
                        "security_verified":False, "live_data_verified":False,
                        "pilot_applied":False, "real_orders":False}
            send("tools/call", {"name":"screener_query","arguments":{"preset":"trending","limit":10}}, 3)
            result = receive(3, 90)
            content = result.get("content")
            if result.get("isError") or not isinstance(content,list) or len(content)!=1 or content[0].get("type")!="text":
                raise ProbeFailure("invalid_screener_tool_result")
            return normalize(json.loads(content[0]["text"]))
        except (ProbeFailure, OSError) as exc:
            if proc.poll() is None and isinstance(exc, ProbeFailure) and exc.reason == "mcp_stdout_closed_or_oversized":
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
            code = proc.poll()
            if code is not None:
                stderr_worker.join(timeout=2)
            detail = dict(exc.detail or {}) if isinstance(exc, ProbeFailure) else {}
            detail.update({"child_exit_code":code,"stderr_categories":classify_stderr(bytes(stderr_tail))})
            raise ProbeFailure(exc.reason if isinstance(exc, ProbeFailure) else "mcp_pipe_failure", detail) from None
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=10)
            proc.stdin.close()
            worker.join(timeout=2)
            stderr_worker.join(timeout=2)
            proc.stdout.close()
            proc.stderr.close()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dexterm-root", required=True)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    try:
        result = probe(args.dexterm_root, args.live)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0 if result["status"] in ("mcp_ready", "diagnostic_complete") else 1
    except ProbeFailure as exc:
        print(json.dumps({"status":"rejected","reason":exc.reason,"detail":exc.detail,
                          "pilot_applied":False,"real_orders":False}))
        return 1
    except (ValueError, TypeError, KeyError, AttributeError, ArithmeticError, OSError, subprocess.SubprocessError, queue.Empty) as exc:
        print(json.dumps({"status":"rejected","error_type":type(exc).__name__,
                          "pilot_applied":False,"real_orders":False}))
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
