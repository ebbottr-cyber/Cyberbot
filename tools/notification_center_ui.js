// Mount with the panel's existing authenticated fetch wrapper.
export function mountNotificationCenter(root, request) {
  if (!root || typeof request !== "function") throw new Error("Panel integration required");
  const make = (tag, text) => { const el = document.createElement(tag); if (text) el.textContent = text; return el; };
  const bell = make("button", "🔔 Bildirimler");
  const panel = make("section");
  panel.hidden = true;
  panel.setAttribute("aria-label", "Bildirim merkezi");
  const filter = make("select");
  filter.setAttribute("aria-label", "Kategori");
  for (const [value, label] of Object.entries({"":"Tümü",news:"Haberler",market:"Piyasalar",data:"Veri",risk:"Risk",ai:"Yapay zekâ",trade:"İşlemler",system:"Sistem",github:"GitHub"})) {
    const option = make("option", label); option.value = value; filter.append(option);
  }
  const unread = make("input"); unread.type = "checkbox";
  const label = make("label", "Sadece okunmamış "); label.append(unread);
  const status = make("p"); status.setAttribute("role", "status");
  const list = make("div");
  const refresh = make("button", "Yenile");
  for (const button of [bell, refresh]) button.type = "button";
  panel.append(filter, label, refresh, status, list);
  root.append(bell, panel);
  let generation = 0;
  async function load() {
    const current = ++generation;
    status.textContent = "Yükleniyor…";
    try {
      const params = new URLSearchParams({unread: String(unread.checked), limit: "100"});
      if (filter.value) params.set("category", filter.value);
      const [response, countResponse] = await Promise.all([
        request("/api/notifications?" + params),
        request("/api/notifications?unread=true&limit=500")
      ]);
      if (!response.ok || !countResponse.ok) throw new Error("Request failed");
      const [data, counts] = await Promise.all([response.json(), countResponse.json()]);
      if (current !== generation) return;
      bell.textContent = "🔔 Bildirimler (" + (counts.items.length === 500 ? "500+" : counts.items.length) + ")";
      list.replaceChildren();
      for (const item of data.items) {
        const article = make("article");
        article.append(make("h3", item.title), make("small", ({critical:"Kritik",warning:"Uyarı",info:"Bilgi"}[item.severity] || "Bilgi") + " · " + item.source),
          make("p", item.body), make("time", new Date(item.created_at).toLocaleString("tr-TR")));
        if (!item.read_at) {
          const read = make("button", "Okundu işaretle"); read.type = "button";
          read.onclick = async () => {
            read.disabled = true;
            try {
              const res = await request("/api/notifications/" + encodeURIComponent(item.id) + "/read", {method:"POST"});
              if (!res.ok) throw new Error("Request failed");
              await load();
            } catch { status.textContent = "Bildirim güncellenemedi."; read.disabled = false; }
          };
          article.append(read);
        }
        list.append(article);
      }
      status.textContent = data.items.length ? "" : "Bildirim bulunamadı.";
    } catch { if (current === generation) status.textContent = "Bildirimler alınamadı."; }
  }
  bell.setAttribute("aria-expanded", "false");
  bell.onclick = () => { panel.hidden = !panel.hidden; bell.setAttribute("aria-expanded", String(!panel.hidden)); if (!panel.hidden) load(); };
  filter.onchange = unread.onchange = refresh.onclick = load;
  load();
  return {refresh: load, destroy() { ++generation; bell.remove(); panel.remove(); }};
}
