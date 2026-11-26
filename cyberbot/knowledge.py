"""Read-only research snapshot and portable Obsidian vault export."""
import hashlib,io,json,zipfile
from .development import overview,MARKETS

def snapshot(mode):
    d=overview(mode)
    nodes=[{"id":"hub","type":"text","x":0,"y":0,"width":300,"height":140,"text":"Cyberbot araştırma hafızası\n"+mode}]
    edges=[]
    for i,m in enumerate(d["markets"]):
        name=m["market"]
        nodes.append({"id":name,"type":"file","file":"Piyasalar/"+name+".md","x":-640+320*i,"y":240,"width":280,"height":160})
        edges.append({"id":"hub-"+name,"fromNode":"hub","toNode":name,"fromSide":"bottom","toSide":"top"})
        for j,x in enumerate(m["latest"]):
            key=note_id(mode,name,x["symbol"])
            nodes.append({"id":key,"type":"file","file":"Arastirmalar/"+key+".md","x":-640+320*i,"y":480+j*180,"width":280,"height":140})
            edges.append({"id":"edge-"+key,"fromNode":name,"toNode":key,"fromSide":"bottom","toSide":"top"})
    return {**d,"canvas":{"nodes":nodes,"edges":edges}}

def note_id(mode,market,symbol):
    return hashlib.sha256(json.dumps([mode,market,symbol]).encode()).hexdigest()[:24]

def prop(value):
    return json.dumps(value,ensure_ascii=False,allow_nan=False)

def vault_zip(mode):
    d=snapshot(mode)
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w",compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("Baslangic.md","# Cyberbot Vault\n\nSalt okunur araştırma anlık görüntüsü. SQLite ana kaynaktır.\n\nVeri modu: "+mode+"\n\n"+"\n".join("- [[Piyasalar/"+m["market"]+"]]" for m in d["markets"])+"\n\n![[Arastirmalar.base]]\n")
        z.writestr("Cyberbot.canvas",json.dumps(d["canvas"],ensure_ascii=False,indent=2))
        from .news_graph import canvas_summary
        z.writestr("Haberler.canvas",json.dumps(canvas_summary(),ensure_ascii=False,indent=2))
        z.writestr("Arastirmalar.base",'''filters:
  and:
    - 'file.inFolder("Arastirmalar")'
views:
  - type: table
    name: "Araştırmalar"
    order:
      - market
      - symbol
      - mode
      - regime
      - shadow_return_pct
      - shadow_drawdown_pct
      - candidate
      - created_at
''')
        z.writestr("Kurallar.md","# Araştırma kuralları\n\n- Sentetik veri gerçek piyasa kanıtı değildir.\n- Karantina, model ve strateji puanları araştırma içindir.\n- Notlar emir veya ayar komutu değildir.\n- Kaynak ve zaman bilgisi korunur.\n- Aynı deney bağımsız kanıt olarak sayılmaz.\n")
        for m in d["markets"]:
            links=[]
            for x in m["latest"]:
                key=note_id(mode,m["market"],x["symbol"])
                links.append("- [[Arastirmalar/"+key+"]]")
                props={"market":m["market"],"symbol":x["symbol"],"mode":mode,"regime":x["regime"],"candidate":x["candidate_after_quarantine"],"created_at":x["created_at"],"experiment_id":x["id"],"shadow_return_pct":(x["shadow"] or {}).get("return_pct"),"shadow_drawdown_pct":(x["shadow"] or {}).get("drawdown_pct")}
                # JSON scalar syntax is safe YAML frontmatter; arbitrary text is not rendered as Markdown.
                content="---\n"+"\n".join(k+": "+prop(v) for k,v in props.items())+"\n---\n\n# Araştırma kaydı\n\n[[Piyasalar/"+m["market"]+"]] · [[Kurallar]]\n\nBu kayıt deney anlık görüntüsüdür.\n"
                z.writestr("Arastirmalar/"+key+".md",content)
                z.writestr("Kayitlar/"+key+".json",json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False))
            z.writestr("Piyasalar/"+m["market"]+".md","# "+m["market"]+"\n\n[[Baslangic]]\n\nKayıtlı deney: "+str(m["experiments"])+"\n\n"+"\n".join(links))
    return buf.getvalue()
