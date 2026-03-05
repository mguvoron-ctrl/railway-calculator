import asyncio
import json
import os
from urllib.parse import quote

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response

# ============ CONFIG ============
ALTA_URL   = "https://www.alta.ru/rail_tracking/engine.php"
CACHE_FILE = "cache.json"
BACKUP_KEY = os.getenv("BACKUP_KEY", "")
PROXIES    = [
    "https://corsproxy.io/?",
    "https://api.codetabs.com/v1/proxy/?quest=",
]

# ============ APP ============
app = FastAPI(title="ЖД Калькулятор")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ============ CACHE ============
def load_cache() -> dict:
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def save_cache(cache: dict) -> None:
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
    except Exception:
        pass

def make_key(src: str, dst: str) -> str:
    a = " ".join(src.split())
    b = " ".join(dst.split())
    lo, hi = sorted([a, b])
    return f"{lo}||{hi}"

def extract_segments(data: dict) -> list:
    for item in data.values():
        if isinstance(item, dict) and isinstance(item.get("route"), list):
            return item["route"]
    return []

def expand_cache(segments: list) -> None:
    """Кэшировать все подмаршруты из маршрута."""
    if not segments:
        return
    stations = []
    for s in segments:
        if not stations:
            stations.append((s["st1_ecp"], s.get("name1", "")))
        stations.append((s["st2_ecp"], s.get("name2", "")))

    n = len(stations)
    for i in range(n):
        dist, sub = 0, []
        for j in range(i + 1, n):
            seg = segments[j - 1]
            dist += seg.get("rst", 0)
            sub.append(seg)
            src_str = " ".join(f"{stations[i][0]} {stations[i][1]}".split())
            dst_str = " ".join(f"{stations[j][0]} {stations[j][1]}".split())
            key = make_key(src_str, dst_str)
            if key not in _cache:
                _cache[key] = {"1": {"route": list(sub), "total_rst": dist,
                                     "src": stations[i][0], "dst": stations[j][0]}}

_cache: dict = load_cache()

# ============ ALTA FETCHING ============
async def _fetch_alta(client: httpx.AsyncClient, src: str, dst: str) -> dict:
    r = await client.get(ALTA_URL, params={"action": "get_route", "src": src, "dst": dst})
    r.raise_for_status()
    return r.json()

async def _fetch_proxy(client: httpx.AsyncClient, proxy: str, src: str, dst: str) -> dict:
    url = f"{proxy}{ALTA_URL}?action=get_route&src={quote(src)}&dst={quote(dst)}"
    r = await client.get(url)
    r.raise_for_status()
    return r.json()

async def fetch_route(src: str, dst: str) -> dict:
    """Запрос к alta.ru — гонка прямого запроса и прокси."""
    async with httpx.AsyncClient(timeout=12) as client:
        tasks = [_fetch_alta(client, src, dst)] + \
                [_fetch_proxy(client, p, src, dst) for p in PROXIES]
        for coro in asyncio.as_completed(tasks):
            try:
                data = await coro
                if data and extract_segments(data):
                    return data
            except Exception:
                continue
    return {}

# ============ ROUTES ============
async def async_save_cache():
    """Асинхронное сохранение — не блокирует ответ пользователю."""
    import asyncio as _asyncio
    await _asyncio.get_event_loop().run_in_executor(None, lambda: save_cache(_cache))

@app.get("/api/route")
async def get_route(src: str, dst: str):
    key = make_key(src, dst)
    if key in _cache:
        return _cache[key]
    data = await fetch_route(src, dst)
    if not data:
        raise HTTPException(504, "Маршрут не найден — alta.ru не ответил")
    _cache[key] = data
    expand_cache(extract_segments(data))
    asyncio.create_task(async_save_cache())
    return data


@app.get("/backup")
async def backup_download(key: str = ""):
    """Скачать кэш (защищён паролем)."""
    if not BACKUP_KEY or key != BACKUP_KEY:
        raise HTTPException(403, "Доступ запрещён")
    data = json.dumps(_cache, ensure_ascii=False, indent=2).encode("utf-8")
    return Response(content=data, media_type="application/json",
                    headers={"Content-Disposition": "attachment; filename=cache.json"})


@app.post("/upload-cache")
async def upload_cache(request: Request, key: str = ""):
    """Загрузить кэш на сервер (защищён паролем)."""
    if not BACKUP_KEY or key != BACKUP_KEY:
        raise HTTPException(403, "Доступ запрещён")
    try:
        body = await request.body()
        data = json.loads(body)
        _cache.clear()
        _cache.update(data)
        save_cache(_cache)
        return {"status": "ok", "cached_routes": len(_cache)}
    except Exception as e:
        raise HTTPException(400, f"Ошибка: {e}")


@app.get("/health")
async def health():
    return {"status": "ok", "cached_routes": len(_cache)}


@app.on_event("shutdown")
async def shutdown():
    save_cache(_cache)


@app.get("/")
async def root():
    return FileResponse("index.html")
