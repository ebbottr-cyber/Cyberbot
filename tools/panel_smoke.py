"""Chromium smoke tests against isolated local fixtures; no live financial network."""
import os,sys,time,tempfile,subprocess,socket
from pathlib import Path
from urllib.request import urlopen
from playwright.sync_api import sync_playwright,expect
PAGES=("/", "/data", "/analysis", "/strategies", "/learning", "/models", "/development", "/futures", "/health", "/knowledge", "/news", "/stress", "/traders")
def main():
    with tempfile.TemporaryDirectory(prefix="cyberbot-panel-") as tmp:
        root=Path(tmp)
        with socket.socket() as s:s.bind(("127.0.0.1",0));port=s.getsockname()[1]
        origin=f"http://127.0.0.1:{port}"
        env={k:v for k,v in os.environ.items() if not k.startswith("CYBERBOT_")}
        env.update(CYBERBOT_DB=str(root/"paper.sqlite3"),CYBERBOT_LEARNING_DB=str(root/"learning.sqlite3"),CYBERBOT_WORKER_DB=str(root/"worker.sqlite3"))
        with (root/"server.log").open("w+",encoding="utf-8") as log:
            process=subprocess.Popen([sys.executable,"-m","uvicorn","cyberbot.api:app","--host","127.0.0.1","--port",str(port),"--no-proxy-headers"],env=env,stdout=log,stderr=log)
            try:
                for _ in range(100):
                    try:
                        with urlopen(origin+"/",timeout=1) as response:
                            if response.status==200:break
                    except OSError:
                        if process.poll() is not None:raise RuntimeError("Server exited")
                        time.sleep(.1)
                else:raise RuntimeError("Server not ready")
                with sync_playwright() as p:
                    browser=p.chromium.launch()
                    for size in ({"width":1280,"height":900},{"width":390,"height":844},{"width":320,"height":700}):
                        context=browser.new_context(viewport=size,service_workers="block")
                        context.route("**/*",lambda route:route.continue_() if route.request.url.startswith(origin+"/") else route.abort())
                        page=context.new_page();errors=[];failed=[]
                        page.on("pageerror",lambda exc:errors.append(str(exc)))
                        page.on("response",lambda res:failed.append(res.url) if res.status>=500 else None)
                        for path in PAGES:
                            response=page.goto(origin+path,wait_until="networkidle")
                            assert response.status==200,(path,response.status)
                            assert page.locator("main").count()==1,path
                            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2"),(path,size,"horizontal overflow")
                            assert not errors,(path,errors)
                            assert not failed,(path,failed)
                            if path=="/":
                                expect(page.locator("#marketCards .card")).to_have_count(5)
                                page.locator("#chartMarket").select_option("FUTURES")
                                expect(page.locator("#chartNote")).to_contain_text("USDT")
                            if path=="/models":
                                expect(page.locator("#summary")).to_be_disabled()
                                expect(page.locator("#chronosRun")).to_be_disabled()
                            if path=="/data":expect(page.locator("#scan")).to_be_disabled()
                        if size["width"]==390:
                            page.goto(origin+"/",wait_until="networkidle")
                            context.set_offline(True)
                            expect(page.locator("#equity")).to_have_text("—")
                            expect(page.locator("#marketCards .card")).to_have_count(0)
                            expect(page.locator("#newsOverviewStatus")).to_contain_text("Bağlantı yok")
                            context.set_offline(False)
                            expect(page.locator("#marketCards .card")).to_have_count(5,timeout=10000)
                            assert not errors,errors
                        print("PASS",size,len(PAGES),"pages",flush=True)
                        context.close()
                    browser.close()
            except BaseException:
                log.flush();log.seek(0);print(log.read()[-12000:]);raise
            finally:
                process.terminate()
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:process.kill();process.wait()
if __name__=="__main__":main()
