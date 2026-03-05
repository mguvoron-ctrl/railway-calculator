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
