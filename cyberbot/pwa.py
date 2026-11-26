"""Installable shell only. No financial data or credential caching."""
import struct
import zlib
from functools import lru_cache
from pathlib import Path
from fastapi import APIRouter,HTTPException
from fastapi.responses import Response,JSONResponse

router=APIRouter()
WEB=Path(__file__).parent/"web"

@lru_cache(maxsize=3)
def icon_png(size):
    # Original geometric Obsidian mark on an opaque navy background.
    def chunk(tag,data):
        return struct.pack(">I",len(data))+tag+data+struct.pack(">I",zlib.crc32(tag+data)&0xffffffff)
    raw=bytearray()
    for y in range(size):
        raw.append(0)
        for x in range(size):
            u=(x+.5)/size-.5;v=(y+.5)/size-.5
            diamond=abs(u)+abs(v)
            rgb=(11,16,24)
            if .19<diamond<.33:rgb=(45,212,191)
            elif diamond<=.19:rgb=(21,30,43)
            if abs(u)<.038 and abs(v)<.13:rgb=(94,234,212)
            raw.extend(rgb)
    return b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",size,size,8,2,0,0,0))+chunk(b"IDAT",zlib.compress(raw,9))+chunk(b"IEND",b"")

@router.get("/manifest.webmanifest")
def manifest():
    return JSONResponse({"id":"/","name":"Cyberbot Obsidian","short_name":"Obsidian","lang":"tr",
        "start_url":"/","scope":"/","display":"standalone","background_color":"#0b1018","theme_color":"#0b1018",
        "icons":[{"src":f"/pwa/icon-{n}.png","sizes":f"{n}x{n}","type":"image/png","purpose":"any"} for n in (192,512)]+[{"src":"/pwa/icon-512.png","sizes":"512x512","type":"image/png","purpose":"maskable"}]},
        media_type="application/manifest+json")

@router.get("/pwa/icon-{size}.png")
def icon(size:int):
    if size not in (180,192,512):raise HTTPException(404)
    return Response(icon_png(size),media_type="image/png")

@router.get("/sw.js")
def worker():
    return Response((WEB/"sw.js").read_text(encoding="utf-8"),media_type="application/javascript",
                    headers={"Service-Worker-Allowed":"/"})
