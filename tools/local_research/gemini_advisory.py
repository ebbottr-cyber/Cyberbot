"""Opt-in Gemini advisory research. No market data, orders or paid fallback."""
import http.client
import json
import os
from pathlib import Path
import sqlite3
from contextlib import closing
import time

VERSION = "gemini-advisory-1"
DAILY_LIMIT = 5
MIN_INTERVAL = 1800
MAX_OUTPUT_BYTES = 65536
MODELS = {"gemini-3.1-flash-lite"}
MARKETS = {"BIST", "NASDAQ", "XETRA", "FUTURES", "SOLANA"}
TOPICS = {"volatility", "liquidity", "data_quality", "model_validation"}
RISKS = {"low", "medium", "high", "unknown"}
CHECKS = {"check_data", "check_spread", "check_regime", "check_validation", "defer"}


def request_body(market, topic):
    if market not in MARKETS or topic not in TOPICS:
        raise ValueError("unsupported advisory context")
    # Fixed categories only: no user text, symbols, prices, news articles,
    # holdings, strategy parameters, or local model outputs.
    prompt = ("Provide a generic educational research checklist for market "
              + market + " and topic " + topic +
              ". You have no current market information. Return only JSON "
              'with keys risk and checks. risk must be unknown. checks must '
              'contain 1 to 3 distinct items from check_data, check_spread, '
              'check_regime, check_validation, defer. No trade advice.')
    return {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 512,
                                 "responseMimeType": "application/json",
                                 "temperature": 0}}


def reserve(db, now):
    """Reserve before transport, count failed attempts, never refund quota."""
    if not isinstance(now, int) or now < 0:
        raise ValueError("invalid clock")
    db.execute("BEGIN IMMEDIATE")
    try:
        db.execute("""CREATE TABLE IF NOT EXISTS attempts (
            id INTEGER PRIMARY KEY, at INTEGER NOT NULL, status TEXT NOT NULL
        )""")
        latest = db.execute("SELECT at,status FROM attempts ORDER BY id DESC LIMIT 1").fetchone()
        if latest and now < latest[0]:
            db.rollback()
            return None, "CLOCK_REVIEW"
        if latest and latest[1] in ("HTTP_401","HTTP_403","HTTP_429"):
            db.rollback()
            return None, "PROVIDER_REVIEW_REQUIRED"
        if latest and now-latest[0] < MIN_INTERVAL:
            db.rollback()
            return None, "WAIT_INTERVAL"
        count = db.execute("SELECT COUNT(*) FROM attempts WHERE at>?",
                           (now-86400,)).fetchone()[0]
        if count >= DAILY_LIMIT:
            db.rollback()
            return None, "LOCAL_QUOTA_EXHAUSTED"
        cur = db.execute("INSERT INTO attempts(at,status) VALUES (?,?)",
                         (now,"RESERVED"))
        attempt = cur.lastrowid
        db.commit()
        return attempt,"RESERVED"
    except BaseException:
        db.rollback()
        raise


def decode(payload):
    candidate = payload["candidates"][0]
    if candidate.get("finishReason") != "STOP":
        raise ValueError("incomplete advisory")
    parts = candidate["content"]["parts"]
    text = "".join(p["text"] for p in parts if "text" in p and not p.get("thought"))
    result = json.loads(text)
    if not isinstance(result, dict) or set(result) != {"risk","checks"}:
        raise ValueError("unexpected response")
    checks = result["checks"]
    if (result["risk"] != "unknown" or not isinstance(checks,list)
            or not 1 <= len(checks) <= 3
            or any(type(x) is not str or x not in CHECKS for x in checks)
            or len(set(checks)) != len(checks)):
        raise ValueError("invalid advisory")
    return result


def transport(model, key, body):
    if model not in MODELS:
        raise ValueError("model not allowed")
    conn = http.client.HTTPSConnection("generativelanguage.googleapis.com",timeout=20)
    try:
        conn.request("POST","/v1beta/models/"+model+":generateContent",
                     body=json.dumps(body).encode(),
                     headers={"Content-Type":"application/json","x-goog-api-key":key})
        response = conn.getresponse()
        if response.status != 200:
            return response.status, None
        raw = response.read(MAX_OUTPUT_BYTES+1)
        if len(raw)>MAX_OUTPUT_BYTES:
            raise ValueError("response too large")
        return response.status,json.loads(raw)
    finally:
        conn.close()


def advise(root, market, topic, *, env=None, send=transport, clock=time.time):
    env = os.environ if env is None else env
    base = {"version":VERSION,"market":market,"topic":topic,
            "advisory_only":True,"real_orders":False,"automatic_promotion":False}
    body = request_body(market,topic)
    if (env.get("CYBERBOT_GEMINI_ENABLED") != "1"
            or env.get("CYBERBOT_GEMINI_FREE_PROJECT_CONFIRMED") != "1"
            or env.get("CYBERBOT_GEMINI_DATA_POLICY_ACCEPTED") != "1"):
        return {**base,"status":"DISABLED"}
    model = env.get("CYBERBOT_GEMINI_MODEL","")
    key = env.get("CYBERBOT_GEMINI_API_KEY","")
    if model not in MODELS or not key or len(key)>256:
        return {**base,"status":"CONFIGURATION_REQUIRED"}
    folder = Path(root)/"var/ai"
    folder.mkdir(parents=True,exist_ok=True)
    path = folder/"gemini-quota.sqlite3"
    if path.is_symlink() or (path.exists() and path.stat().st_nlink != 1):
        raise ValueError("unsafe quota path")
    with closing(sqlite3.connect(path,timeout=10)) as db:
        attempt,status = reserve(db,int(clock()))
        if attempt is None:
            return {**base,"status":status}
        result = None
        try:
            code,payload = send(model,key,body)
            if code == 200:
                result = decode(payload)
                status = "OK"
            else:
                status = "HTTP_"+str(code) if type(code) is int and 100<=code<=599 else "PROVIDER_ERROR"
        except Exception:
            # Never expose credentials, request details or upstream error bodies.
            status = "PROVIDER_ERROR"
        with db:
            db.execute("UPDATE attempts SET status=? WHERE id=?",(status,attempt))
    return {**base,"status":status,"advisory":result}
