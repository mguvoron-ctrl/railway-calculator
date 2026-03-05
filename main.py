from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import httpx

app = FastAPI(title="ЖД Калькулятор")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

ALTA_URL = "https://www.alta.ru/rail_tracking/engine.php"

# Кэш в памяти сервера — общий для всех пользователей
_cache: dict = {}

def cache_key(src: str, dst: str) -> str:
    a, b = sorted([src.strip(), dst.strip()])
    return f"{a}||{b}"

def extract_segments(data: dict) -> list:
    for item in data.values():
        if isinstance(item, dict) and isinstance(item.get("route"), list):
            return item["route"]
    return []

def cache_subroutes(segments: list):
    """Кэширует все подмаршруты.
    Маршрут A→B→C→D даст кэш для всех пар:
    A→B, A→C, A→D, B→C, B→D, C→D (и обратно через sort в cache_key)
    """
    if not segments:
        return

    # Собираем список станций по порядку
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
            # Сегмент между станцией j-1 и j
            seg = segments[j - 1]
            dist += seg.get("rst", 0)
            sub_segs.append(seg)

            src_code, src_name = stations[i]
            dst_code, dst_name = stations[j]
            src_str = f"{src_code} {src_name}".strip()
            dst_str = f"{dst_code} {dst_name}".strip()
            key = cache_key(src_str, dst_str)

            if key not in _cache:
                _cache[key] = {
                    "1": {
                        "route": list(sub_segs),  # копия списка!
                        "total_rst": dist,
                        "src": src_code,
                        "dst": dst_code,
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


@app.get("/")
async def root():
    return FileResponse("index.html")
