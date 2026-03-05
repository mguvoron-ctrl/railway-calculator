from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import httpx
import json
import os

app = FastAPI(title="ЖД Калькулятор")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

ALTA_URL = "https://www.alta.ru/rail_tracking/engine.php"
CACHE_FILE = "cache.json"

# Загружаем кэш с диска при старте
def load_cache() -> dict:
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def save_cache(cache: dict):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
    except Exception:
        pass

_cache: dict = load_cache()

def cache_key(src: str, dst: str) -> str:
    src = " ".join(src.split())
    dst = " ".join(dst.split())
    a, b = sorted([src.strip(), dst.strip()])
    return f"{a}||{b}"

def extract_segments(data: dict) -> list:
    for item in data.values():
        if isinstance(item, dict) and isinstance(item.get("route"), list):
            return item["route"]
    return []

def cache_subroutes(segments: list):
    if not segments:
        return
    stations = []
    for s in segments:
        if not stations:
            stations.append((s["st1_ecp"], s.get("name1", "")))
        stations.append((s["st2_ecp"], s.get("name2", "")))

    n = len(stations)
    for i in range(n):
        dist = 0
        sub_segs = []
        for j in range(i + 1, n):
            seg = segments[j - 1]
            dist += seg.get("rst", 0)
            sub_segs.append(seg)
            src_str = " ".join(f"{stations[i][0]} {stations[i][1]}".split())
            dst_str = " ".join(f"{stations[j][0]} {stations[j][1]}".split())
            key = cache_key(src_str, dst_str)
            if key not in _cache:
                _cache[key] = {
                    "1": {
                        "route": list(sub_segs),
                        "total_rst": dist,
                        "src": stations[i][0],
                        "dst": stations[j][0],
                    }
                }


@app.get("/api/route")
async def get_route(src: str, dst: str):
    key = cache_key(src, dst)
    if key in _cache:
        return _cache[key]
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(ALTA_URL, params={"action": "get_route", "src": src, "dst": dst})
            resp.raise_for_status()
            data = resp.json()
            _cache[key] = data
            cache_subroutes(extract_segments(data))
            save_cache(_cache)
            return data
    except httpx.TimeoutException:
        raise HTTPException(504, "alta.ru не отвечает")
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, "Ошибка alta.ru")
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/health")
async def health():
    return {"status": "ok", "cached_routes": len(_cache)}


@app.get("/debug")
async def debug(src: str, dst: str):
    key = cache_key(src, dst)
    hit = key in _cache
    similar = [k for k in _cache.keys() if src.split()[0] in k or dst.split()[0] in k][:10]
    return {"key": key, "hit": hit, "similar_keys": similar}


@app.get("/")
async def root():
    return FileResponse("index.html")
