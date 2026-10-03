"""Healthcheck: TCP до порта + запрос через прокси с замером пинга."""
from __future__ import annotations

import asyncio
import time


async def tcp_ok(port: int, timeout: float = 2.0) -> bool:
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection("127.0.0.1", port), timeout=timeout
        )
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return True
    except Exception:
        return False


async def proxy_check(profile: dict, timeout: float = 10.0) -> tuple[str, int | None, str | None, str | None]:
    """Возвращает (status, ping_ms, ip, error)."""
    mode = profile.get("mode") or "socks5"
    if mode in ("socks5", "both"):
        port = profile.get("socks_port")
        proxy_url = f"socks5://127.0.0.1:{port}" if port else None
    else:
        port = profile.get("http_port")
        proxy_url = f"http://127.0.0.1:{port}" if port else None

    if not proxy_url:
        return "offline", None, None, "нет порта для проверки"

    if not await tcp_ok(port):
        return "offline", None, None, f"порт {port} не слушается"

    try:
        import httpx
    except ImportError:
        return "online", None, None, "httpx не установлен — только TCP-проверка"

    ip: str | None = None
    ping_ms: int | None = None
    try:
        async with httpx.AsyncClient(proxy=proxy_url, timeout=timeout, trust_env=False) as client:
            t0 = time.perf_counter()
            r = await client.get("https://www.google.com/generate_204")
            ping_ms = int((time.perf_counter() - t0) * 1000)
            if r.status_code not in (200, 204):
                return "offline", ping_ms, None, f"generate_204 вернул {r.status_code}"
            try:
                r2 = await client.get("https://api.ipify.org?format=text")
                if r2.status_code == 200:
                    ip = r2.text.strip()[:64]
            except Exception:
                pass
        return "online", ping_ms, ip, None
    except Exception as e:
        return "offline", None, None, f"{type(e).__name__}: {e}"[:300]
