// No Cache API, IndexedDB, background sync, queued orders or stored financial data.
self.addEventListener('install',event=>{event.waitUntil(self.skipWaiting())});
self.addEventListener('activate',event=>{event.waitUntil(self.clients.claim())});
self.addEventListener('fetch',event=>{
  const req=event.request;
  const url=new URL(req.url);
  if(req.method!=='GET'||req.mode!=='navigate'||url.origin!==self.location.origin||url.pathname.startsWith('/api/'))return;
  // Preserve HTTP errors including authorization. Fallback only if the network fails.
  event.respondWith(fetch(req,{cache:'no-store'}).catch(()=>new Response(
    '<!doctype html><html lang="tr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Obsidian çevrimdışı</title><h1>Bağlantı yok</h1><p>Cyberbot sunucusuna ulaşılamıyor. Veriler ve işlemler çevrimdışı gösterilmez. Bağlantıyı kontrol edip yeniden açın.</p><a href="/">Tekrar dene</a></html>',
    {status:503,headers:{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store','Content-Security-Policy':"default-src 'none'; frame-ancestors 'none'; base-uri 'none'"}}
  )));
});
