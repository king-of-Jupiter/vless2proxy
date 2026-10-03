"""VLESS → SOCKS5 Dashboard: FastAPI, без авторизации (для LAN)."""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from . import db
from . import xray_manager
from .health import proxy_check, tcp_ok
from .subscription import fetch_subscription
from .vless_parser import parse_vless_url, VlessParseError

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "30"))
DASHBOARD_PORT = int(os.environ.get("DASHBOARD_PORT", "8123"))

_health_task: asyncio.Task | None = None


async def health_loop() -> None:
    while True:
        try:
            profiles = await db.list_profiles()
            for p in profiles:
                if not p["enabled"]:
                    continue
                if not xray_manager.is_running(p["id"]):
                    await db.update_health(p["id"], "offline", None, p["last_ip"], "процесс не запущен")
                    continue
                status, ping, ip, err = await proxy_check(p)
                await db.update_health(p["id"], status, ping, ip or p["last_ip"], err)
        except asyncio.CancelledError:
            break
        except Exception:
            pass
        await asyncio.sleep(CHECK_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _health_task
    await db.init_db()
    xray_manager.ensure_dirs()
    # автозапуск включённых профилей
    for p in await db.list_profiles():
        if p["enabled"]:
            try:
                xray_manager.start(p)
            except Exception as e:
                await db.update_health(p["id"], "offline", None, None, str(e)[:300])
    _health_task = asyncio.create_task(health_loop())
    yield
    if _health_task:
        _health_task.cancel()
    for p in await db.list_profiles():
        xray_manager.stop(p["id"])


app = FastAPI(title="VLESS → SOCKS5 Dashboard", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


class ProfileIn(BaseModel):
    name: str = ""
    vless_url: str
    mode: str = Field(default="socks5", pattern="^(socks5|http|both)$")
    socks_port: int | None = None
    http_port: int | None = None


class ProfilePatch(BaseModel):
    name: str | None = None
    vless_url: str | None = None
    mode: str | None = Field(default=None, pattern="^(socks5|http|both)$")
    socks_port: int | None = None
    http_port: int | None = None
    enabled: bool | None = None


def validate_ports(mode: str, socks_port, http_port) -> tuple[int | None, int | None]:
    if mode in ("socks5", "both") and not socks_port:
        raise HTTPException(422, "нужен socks_port")
    if mode in ("http", "both") and not http_port:
        raise HTTPException(422, "нужен http_port")
    if mode == "socks5":
        http_port = None
    if mode == "http":
        socks_port = None
    for port in (socks_port, http_port):
        if port is None:
            continue
        if not (1 <= port <= 65535):
            raise HTTPException(422, f"порт {port} вне диапазона 1-65535")
        if port == DASHBOARD_PORT:
            raise HTTPException(422, f"порт {port} занят дашбордом")
    return socks_port, http_port


def enrich(p: dict) -> dict:
    return {**p, "running": xray_manager.is_running(p["id"])}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    profiles = [enrich(p) for p in await db.list_profiles()]
    nxt = await db.next_ports()
    return templates.TemplateResponse(
        request,
        "index.html",
        {"profiles": profiles, "next_ports": nxt, "dashboard_port": DASHBOARD_PORT},
    )


@app.get("/api/profiles")
async def api_list():
    return [enrich(p) for p in await db.list_profiles()]


@app.get("/api/next-ports")
async def api_next_ports():
    return await db.next_ports()


class ValidateIn(BaseModel):
    vless_url: str
    mode: str = Field(default="socks5", pattern="^(socks5|http|both)$")


@app.post("/api/validate")
async def api_validate(body: ValidateIn):
    """Предпроверка ссылки без сохранения: поднимает временный Xray,
    возвращает online/offline + пинг + egress-IP."""
    try:
        return await xray_manager.ephemeral_check(body.vless_url.strip(), body.mode)
    except VlessParseError as e:
        raise HTTPException(422, f"VLESS: {e}")


class SubscriptionIn(BaseModel):
    url: str


@app.post("/api/subscription/fetch")
async def api_subscription_fetch(body: SubscriptionIn):
    """Скачать подписку, декодировать (base64/plain) и вернуть список серверов."""
    from urllib.parse import urlparse as _urlparse

    u = _urlparse(body.url.strip())
    if u.scheme not in ("http", "https") or not u.hostname:
        raise HTTPException(422, "нужен http(s) URL подписки")
    try:
        servers = await fetch_subscription(body.url.strip())
    except Exception as e:
        raise HTTPException(502, f"не удалось загрузить подписку: {e}"[:300])
    return {"count": len(servers), "servers": servers}


@app.post("/api/profiles")
async def api_create(body: ProfileIn):
    try:
        params = parse_vless_url(body.vless_url)
    except VlessParseError as e:
        raise HTTPException(422, f"VLESS: {e}")
    nxt = await db.next_ports()
    socks_port = body.socks_port or (nxt["socks_port"] if body.mode in ("socks5", "both") else None)
    http_port = body.http_port or (nxt["http_port"] if body.mode in ("http", "both") else None)
    socks_port, http_port = validate_ports(body.mode, socks_port, http_port)
    for port in (s for s in (socks_port, http_port) if s):
        if await db.port_taken(port):
            raise HTTPException(409, f"порт {port} уже используется другим профилем")
        if not xray_manager.port_free(port):
            raise HTTPException(409, f"порт {port} уже занят в системе")
    name = body.name.strip() or params.remark or f"{params.server}:{params.port}"
    p = await db.create_profile(name, body.vless_url.strip(), body.mode, socks_port, http_port)
    try:
        xray_manager.start(p)
        # Проверяем сразу, чтобы карточка не висела в offline/unknown:
        # ждём бинд порта, затем полный прокси-чек с пингом и IP.
        check_port = socks_port or http_port
        for _ in range(25):
            if await tcp_ok(check_port, 0.3):
                break
            await asyncio.sleep(0.2)
        status, ping, ip, err = await proxy_check(p)
        await db.update_health(p["id"], status, ping, ip, err)
    except Exception as e:
        await db.update_health(p["id"], "offline", None, None, str(e)[:300])
    return enrich(await db.get_profile(p["id"]))


@app.put("/api/profiles/{pid}")
async def api_update(pid: int, body: ProfilePatch):
    p = await db.get_profile(pid)
    if not p:
        raise HTTPException(404, "профиль не найден")
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    new = {**p, **fields}
    if "vless_url" in fields:
        try:
            parse_vless_url(new["vless_url"])
        except VlessParseError as e:
            raise HTTPException(422, f"VLESS: {e}")
    socks_port, http_port = validate_ports(new["mode"], new.get("socks_port"), new.get("http_port"))
    for port in (s for s in (socks_port, http_port) if s):
        if await db.port_taken(port, exclude_id=pid):
            raise HTTPException(409, f"порт {port} уже используется другим профилем")
    fields["socks_port"] = socks_port
    fields["http_port"] = http_port
    p = await db.update_profile(pid, fields)
    if p["enabled"]:
        try:
            xray_manager.start(p)
        except Exception as e:
            await db.update_health(pid, "offline", None, None, str(e)[:300])
    else:
        xray_manager.stop(pid)
    return enrich(await db.get_profile(pid))


@app.delete("/api/profiles/{pid}")
async def api_delete(pid: int):
    p = await db.get_profile(pid)
    if not p:
        raise HTTPException(404, "профиль не найден")
    xray_manager.stop(pid)
    await db.delete_profile(pid)
    return {"ok": True}


@app.post("/api/profiles/{pid}/start")
async def api_start(pid: int):
    p = await db.get_profile(pid)
    if not p:
        raise HTTPException(404, "профиль не найден")
    await db.update_profile(pid, {"enabled": True})
    p = await db.get_profile(pid)
    try:
        xray_manager.start(p)
    except Exception as e:
        await db.update_health(pid, "offline", None, None, str(e)[:300])
        raise HTTPException(500, str(e)[:300])
    return enrich(await db.get_profile(pid))


@app.post("/api/profiles/{pid}/stop")
async def api_stop(pid: int):
    p = await db.get_profile(pid)
    if not p:
        raise HTTPException(404, "профиль не найден")
    xray_manager.stop(pid)
    await db.update_profile(pid, {"enabled": False})
    return enrich(await db.get_profile(pid))


@app.post("/api/profiles/{pid}/restart")
async def api_restart(pid: int):
    p = await db.get_profile(pid)
    if not p:
        raise HTTPException(404, "профиль не найден")
    try:
        xray_manager.start(p)
    except Exception as e:
        raise HTTPException(500, str(e)[:300])
    return enrich(await db.get_profile(pid))


@app.post("/api/profiles/{pid}/check")
async def api_check(pid: int):
    p = await db.get_profile(pid)
    if not p:
        raise HTTPException(404, "профиль не найден")
    if not xray_manager.is_running(pid):
        await db.update_health(pid, "offline", None, p["last_ip"], "процесс не запущен")
    else:
        status, ping, ip, err = await proxy_check(p)
        await db.update_health(pid, status, ping, ip or p["last_ip"], err)
    return enrich(await db.get_profile(pid))


@app.get("/api/profiles/{pid}/logs")
async def api_logs(pid: int, n: int = 100):
    p = await db.get_profile(pid)
    if not p:
        raise HTTPException(404, "профиль не найден")
    return {"logs": xray_manager.tail_logs(pid, min(n, 500))}
