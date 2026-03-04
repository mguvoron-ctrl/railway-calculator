from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx

app = FastAPI(title="ЖД Калькулятор")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

ALTA_URL = "https://www.alta.ru/rail_tracking/engine.php"


@app.get("/api/route")
async def get_route(src: str, dst: str):
    """Рассчитать расстояние между станциями"""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(ALTA_URL, params={
                "action": "get_route",
                "src": src,
                "dst": dst,
            })
            resp.raise_for_status()
            return resp.json()
    except httpx.TimeoutException:
        raise HTTPException(504, "alta.ru не отвечает")
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, "Ошибка alta.ru")
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/health")
async def health():
    return {"status": "ok"}
