"""Chromium smoke tests against isolated local fixtures; no live financial network."""
import os,sys,time,tempfile,subprocess,socket
from pathlib import Path
from urllib.request import urlopen
from playwright.sync_api import sync_playwright,expect
PAGES=("/", "/data", "/analysis", "/strategies", "/learning", "/models", "/development", "/futures", "/health", "/knowledge", "/news", "/stress", "/traders", "/pilot")
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
                                expect(page.locator("#centralMarketRows .card")).to_have_count(5)
                                expect(page.locator("#centralPortfolioRows .card")).to_have_count(5)
                                page.locator("#chartMarket").select_option("FUTURES")
                                expect(page.locator("#chartNote")).to_contain_text("USDT")
                            if path=="/models":
                                expect(page.locator("#summary")).to_be_disabled()
                                expect(page.locator("#chronosRun")).to_be_disabled()
                                page.locator("#aiResearchRefresh").click()
                                expect(page.locator("#aiResearchMessage")).to_contain_text("Rapor okundu",timeout=30000)
                                expect(page.locator("#aiResearchRows tr")).to_have_count(17)
                                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2"),(path,size,"AI report overflow")
                            if path=="/data":expect(page.locator("#scan")).to_be_disabled()
                        if size["width"]==390:
                            page.goto(origin+"/",wait_until="networkidle")
                            # Exercise read coalescing without touching financial endpoints.
                            probe_requests=[]
                            def probe(route):
                                probe_requests.append(route.request.url)
                                route.fulfill(json={"probe":True})
                            page.route("**/api/panel-test-probe",probe)
                            assert page.evaluate("""async()=>{const [a,b]=await Promise.all([api('/api/panel-test-probe'),api('/api/panel-test-probe')]);return a.probe&&b.probe}""")
                            assert len(probe_requests)==1,probe_requests
                            assert page.evaluate("api('/api/panel-test-probe').then(d=>d.probe)")
                            assert len(probe_requests)==2,probe_requests
                            page.unroute("**/api/panel-test-probe")
                            page.route("**/api/panel-test-probe",lambda route:route.fulfill(status=400,json={"detail":"test failure"}))
                            assert page.evaluate("api('/api/panel-test-probe').then(()=>false,e=>e.message==='test failure')")
                            page.unroute("**/api/panel-test-probe")
                            page.route("**/api/panel-test-probe",probe)
                            assert page.evaluate("api('/api/panel-test-probe').then(d=>d.probe)")
                            page.unroute("**/api/panel-test-probe")
                            # Accelerate only the read timeout, keeping actual AbortSignal behavior.
                            assert page.evaluate("""async()=>{
                                const originalFetch=window.fetch, originalTimeout=window.setTimeout;
                                window.setTimeout=(fn,ms,...args)=>originalTimeout(fn,ms===15000?20:ms,...args);
                                window.fetch=(url,options)=>url==='/api/panel-timeout-probe'
                                    ?new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')),{once:true}))
                                    :originalFetch(url,options);
                                try {
                                    return await api('/api/panel-timeout-probe').then(()=>false,e=>e.message.includes('zaman aşımına')) &&
                                        !pendingDashboardReads.has('/api/panel-timeout-probe');
                                } finally {window.fetch=originalFetch;window.setTimeout=originalTimeout}
                            }""")
                            # Simulate a hidden document and advance the browser clock.
                            page.clock.install()
                            page.evaluate("""()=>{Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});document.dispatchEvent(new Event('visibilitychange'))}""")
                            background_reads=[]
                            def record_background(request):
                                if "/api/" in request.url:background_reads.append(request.url)
                            page.on("request",record_background)
                            page.clock.run_for(61000)
                            assert not background_reads,background_reads
                            page.evaluate("""()=>{delete document.hidden;document.dispatchEvent(new Event('visibilitychange'))}""")
                            expect(page.locator("#marketCards .card")).to_have_count(5)
                            page.remove_listener("request",record_background)
                            context.set_offline(True)
                            expect(page.locator("#equity")).to_have_text("—")
                            expect(page.locator("#marketCards .card")).to_have_count(0)
                            expect(page.locator("#newsOverviewStatus")).to_contain_text("Bağlantı yok")
                            context.set_offline(False)
                            expect(page.locator("#marketCards .card")).to_have_count(5,timeout=10000)
                            expect(page.locator("#centralMarketRows .card")).to_have_count(5,timeout=10000)
                            expect(page.locator("#centralPortfolioRows .card")).to_have_count(5,timeout=10000)
                            assert not errors,errors
                        print("PASS",size,len(PAGES),"pages",flush=True)
                        context.close()
                    # Exercise the actual service worker, unlike layout-only contexts.
                    context=browser.new_context(viewport={"width":390,"height":844},service_workers="allow")
                    page=context.new_page()
                    page.goto(origin+"/",wait_until="networkidle")
                    page.wait_for_function("navigator.serviceWorker.controller !== null")
                    expect(page.locator("#pwaStatus")).not_to_contain_text("hazırlanıyor")
                    assert page.evaluate("caches.keys().then(keys => keys.length)") == 0
                    expect(page.locator("#pwaUiRevision")).to_have_text(__import__("re").compile(r"^[a-f0-9]{16}$"))
                    expect(page.locator(".mobile-bottom-nav a[aria-current]")).to_have_attribute("href","#overview")
                    page.locator(".mobile-bottom-nav a[href='#markets']").click()
                    expect(page.locator(".mobile-bottom-nav a[aria-current]")).to_have_attribute("href","#markets")
                    page.route("**/pwa/version",lambda route:route.fulfill(json={"ui_revision":"ffffffffffffffff"}))
                    page.locator("#pwaCheckUpdate").click()
                    expect(page.locator("#pwaReload")).to_be_visible()
                    expect(page.locator("#pwaUpdateStatus")).to_contain_text("Yeni arayüz sürümü")
                    page.unroute("**/pwa/version")
                    context.set_offline(True)
                    expect(page.locator("#equity")).to_have_text("—")
                    expect(page.locator("#pwaStatus")).to_contain_text("Bağlantı yok")
                    expect(page.locator("#homeMarketOverview")).to_be_empty()
                    expect(page.locator("#homeRiskRows")).to_be_empty()
                    expect(page.locator("#homeResearchStatus")).to_contain_text("Bağlantı yok")
                    expect(page.locator("#homeWorkerStatus")).to_contain_text("Bağlantı yok")
                    for selector in ("#centralMarketRows","#centralPortfolioRows","#centralAiRows"):
                        expect(page.locator(selector)).to_be_empty()
                    expect(page.locator("#centralNotificationStatus")).to_contain_text("Bağlantı yok")
                    assert page.evaluate("fetch('/api/portfolio/status').then(()=>false,()=>true)")
                    response=page.goto(origin+"/development")
                    assert response.status==503
                    expect(page.locator("h1")).to_have_text("Bağlantı yok")
                    assert page.evaluate("caches.keys().then(keys => keys.length)") == 0
                    context.set_offline(False)
                    page.get_by_role("link",name="Tekrar dene").click()
                    expect(page.locator("#marketCards .card")).to_have_count(5)
                    context.close()
                    print("PASS PWA worker offline isolation and recovery",flush=True)
                    browser.close()
            except BaseException:
                log.flush();log.seek(0);print(log.read()[-12000:]);raise
            finally:
                process.terminate()
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:process.kill();process.wait()
if __name__=="__main__":main()
