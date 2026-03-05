from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import httpx
import json
import os
import smtplib
import asyncio
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime

app = FastAPI(title="ЖД Калькулятор")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

ALTA_URL = "https://www.alta.ru/rail_tracking/engine.php"
CACHE_FILE = "cache.json"

# Настройки почты — берём из переменных окружения Render
EMAIL_FROM = os.getenv("EMAIL_FROM", "e.a.voronov@yandex.ru")
EMAIL_TO = os.getenv("EMAIL_TO", "e.a.voronov@yandex.ru")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")


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

def send_cache_backup():
    """Отправляет cache.json на почту"""
    if not EMAIL_PASSWORD:
        return
    try:
        data = json.dumps(_cache, ensure_ascii=False, indent=2).encode("utf-8")
        date_str = datetime.now().strftime("%Y-%m-%d")

        msg = MIMEMultipart()
        msg["From"] = EMAIL_FROM
        msg["To"] = EMAIL_TO
        msg["Subject"] = f"ЖД Калькулятор — резервная копия кэша {date_str}"

        msg.attach(MIMEText(f"Резервная копия кэша маршрутов.\nМаршрутов в базе: {len(_cache)}", "plain", "utf-8"))

        part = MIMEBase("application", "octet-stream")
        part.set_payload(data)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename=cache_{date_str}.json")
        msg.attach(part)

        with smtplib.SMTP_SSL("smtp.yandex.ru", 465) as server:
            server.login(EMAIL_FROM, EMAIL_PASSWORD)
            server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
    except Exception as e:
        print(f"Ошибка отправки почты: {e}")

_cache: dict = load_cache()
_last_backup_half: int = -1

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

def maybe_send_daily_backup():
    """Отправляет бэкап каждые 12 часов"""
    global _last_backup_half
    now = datetime.now()
    half = now.day * 2 + (1 if now.hour >= 12 else 0)
    if half != _last_backup_half:
        _last_backup_half = half
        send_cache_backup()


@app.get("/api/route")
async def get_route(src: str, dst: str):
    global _last_backup_half
    key = cache_key(src, dst)
    if key in _cache:
        maybe_send_daily_backup()
        return _cache[key]
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(ALTA_URL, params={"action": "get_route", "src": src, "dst": dst})
            resp.raise_for_status()
            data = resp.json()
            _cache[key] = data
            cache_subroutes(extract_segments(data))
            save_cache(_cache)
            maybe_send_daily_backup()
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
