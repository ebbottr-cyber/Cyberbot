"""Real Chromium desktop/mobile test against guarded Cyberbot ASGI app."""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from playwright.sync_api import sync_playwright


def main():
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder)
        snapshot=root/"snapshot.json"
        snapshot.write_text(json.dumps(dict(schema_version=1,status="research_only",
            generated_at=datetime.now(timezone.utc).isoformat(),real_orders=False,
            execution_allowed=False,markets=[],portfolios=[],instruments=[
                dict(market="TEFAS",symbol="FIXTURE_TR",category="fixture",status="research_review"),
                dict(market="ETF",symbol="FIXTURE_ETF",sector="fixture",status="research_review")])),
            encoding="utf-8")
        env=dict(os.environ,CYBERBOT_FUND_ETF_SNAPSHOT=str(snapshot))
        proc=subprocess.Popen([sys.executable,"-m","uvicorn","cyberbot.api:app","--host","127.0.0.1","--port","18791"],
                              env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        url="http://127.0.0.1:18791"
        try:
            for _ in range(100):
                if proc.poll() is not None:
                    raise RuntimeError("server exited")
                try:
                    with urllib.request.urlopen(url+"/api/fund-etf",timeout=1) as response:
                        assert response.status==200
                    break
                except OSError:
                    time.sleep(.1)
            else:
                raise RuntimeError("server unavailable")
            with sync_playwright() as p:
                browser=p.chromium.launch()
                for width,height in ((1440,900),(390,844)):
                    page=browser.new_page(viewport={"width":width,"height":height},is_mobile=width<500,
                                          has_touch=width<500)
                    page.goto(url+"/")
                    menu=page.locator('#mobileModules a[href="/fund-etf"]')
                    assert menu.count()==1, "Fund ETF menu missing or duplicated"
                    assert page.locator('#mobileModules a[href="/futures"]').count()==1
                    page.goto(url+"/development")
                    assert page.locator("#fundDevelopment").count()==1
                    page.locator("#fundDevCounters .card").first.wait_for()
                    assert page.locator("#fundDevCounters .card").count()==2
                    page.goto(url+"/fund-etf")
                    page.get_by_text("TEFAS / FIXTURE_TR").wait_for()
                    assert page.get_by_text("ETF / FIXTURE_ETF").count()==0
                    page.locator("#tab-etf").click()
                    page.get_by_text("ETF / FIXTURE_ETF").wait_for()
                    assert page.get_by_text("TEFAS / FIXTURE_TR").count()==0
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    assert page.request.get(url+"/manifest.webmanifest").ok
                    assert page.request.get(url+"/sw.js").ok
                    assert page.request.get(url+"/api/fund-etf").headers.get("cache-control")=="no-store"
                    page.close()
                browser.close()
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill();proc.wait()
    print("Fund ETF desktop/mobile Chromium smoke passed")


if __name__=="__main__":
    main()
