import asyncio
import json
import os
from urllib.parse import quote

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response

# ============ CONFIG ============
ALTA_URL    = "https://www.alta.ru/rail_tracking/engine.php"
BACKUP_KEY  = os.getenv("BACKUP_KEY", "")
REDIS_URL   = os.getenv("UPSTASH_REDIS_REST_URL", "")
REDIS_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")
PROXIES     = [
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

# ============ REDIS ============
async def redis_get(key: str) -> str | None:
    if not REDIS_URL:
        return None
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(
                f"{REDIS_URL}/get/{key}",
                headers={"Authorization": f"Bearer {REDIS_TOKEN}"}
            )
            data = r.json()
            return data.get("result")
    except Exception:
        return None

async def redis_set(key: str, value: str) -> None:
    if not REDIS_URL:
        return
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            await client.post(
                f"{REDIS_URL}/set/{key}",
                headers={"Authorization": f"Bearer {REDIS_TOKEN}",
                         "Content-Type": "application/json"},
                content=json.dumps(value)
            )
    except Exception:
        pass

async def redis_keys(pattern: str = "*") -> list:
    if not REDIS_URL:
        return []
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(
                f"{REDIS_URL}/keys/{pattern}",
                headers={"Authorization": f"Bearer {REDIS_TOKEN}"}
            )
            return r.json().get("result", [])
    except Exception:
        return []

# ============ LOCAL CACHE (in-memory) ============
_cache: dict = {}

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
@app.get("/api/route")
async def get_route(src: str, dst: str):
    key = make_key(src, dst)

    # 1. Проверяем in-memory кэш
    if key in _cache:
        return _cache[key]

    # 2. Проверяем Redis
    cached = await redis_get(key)
    if cached:
        data = json.loads(cached)
        _cache[key] = data
        return data

    # 3. Запрашиваем alta.ru
    data = await fetch_route(src, dst)
    if not data:
        raise HTTPException(504, "Маршрут не найден — alta.ru не ответил")

    # Сохраняем в память и Redis
    _cache[key] = data
    expand_cache(extract_segments(data))

    # Сохраняем все новые подмаршруты в Redis асинхронно
    asyncio.create_task(_save_all_new_to_redis())
    return data

_redis_save_queue: set = set()

async def _save_all_new_to_redis():
    """Сохраняет новые ключи в Redis в фоне."""
    keys_to_save = [k for k in _cache if k not in _redis_save_queue]
    for key in keys_to_save:
        _redis_save_queue.add(key)
        await redis_set(key, json.dumps(_cache[key], ensure_ascii=False))


@app.on_event("startup")
async def startup():
    """Загружаем все ключи из Redis в память при старте."""
    if not REDIS_URL:
        return
    print("Загружаю кэш из Redis...")
    keys = await redis_keys("*")
    print(f"Найдено {len(keys)} ключей в Redis")
    # Загружаем батчами по 50
    BATCH = 50
    for i in range(0, len(keys), BATCH):
        batch = keys[i:i+BATCH]
        tasks = [redis_get(k) for k in batch]
        results = await asyncio.gather(*tasks)
        for k, v in zip(batch, results):
            if v:
                try:
                    _cache[k] = json.loads(v)
                    _redis_save_queue.add(k)
                except Exception:
                    pass
    print(f"Загружено {len(_cache)} маршрутов из Redis")


@app.get("/backup")
async def backup_download(key: str = ""):
    if not BACKUP_KEY or key != BACKUP_KEY:
        raise HTTPException(403, "Доступ запрещён")
    data = json.dumps(_cache, ensure_ascii=False, indent=2).encode("utf-8")
    return Response(content=data, media_type="application/json",
                    headers={"Content-Disposition": "attachment; filename=cache.json"})


@app.post("/upload-cache")
async def upload_cache(request: Request, key: str = ""):
    if not BACKUP_KEY or key != BACKUP_KEY:
        raise HTTPException(403, "Доступ запрещён")
    try:
        body = await request.body()
        data = json.loads(body)
        _cache.clear()
        _cache.update(data)
        # Сохраняем всё в Redis
        for k, v in data.items():
            await redis_set(k, json.dumps(v, ensure_ascii=False))
        return {"status": "ok", "cached_routes": len(_cache)}
    except Exception as e:
        raise HTTPException(400, f"Ошибка: {e}")


@app.get("/health")
async def health():
    return {"status": "ok", "cached_routes": len(_cache)}


@app.get("/")
async def root():
    return FileResponse("index.html")
