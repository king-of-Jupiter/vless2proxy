"""Импорт подписок: скачивание, base64/plain decode, разбор в список серверов."""
from __future__ import annotations

import base64

from .vless_parser import parse_vless_url, VlessParseError
from urllib.parse import unquote


def decode_body(text: str) -> list[str]:
    """Тело подписки -> список строк-ссылок.

    Поддерживает два формата:
    - base64: одна длинная строка без '://' (стандарт v2ray-субскрипшенов);
    - plain: ссылки построчно открытым текстом.
    """
    s = (text or "").strip()
    if not s:
        return []
    lines = [line.strip() for line in s.splitlines() if line.strip()]
    if len(lines) == 1 and "://" not in lines[0]:
        try:
            b64 = lines[0].replace("-", "+").replace("_", "/")
            b64 += "=" * (-len(b64) % 4)
            decoded = base64.b64decode(b64).decode("utf-8", errors="replace")
            alt = [line.strip() for line in decoded.splitlines() if line.strip()]
            if alt:
                return alt
        except Exception:
            pass
    return lines


def parse_servers(lines: list[str]) -> list[dict]:
    """Строки -> дескрипторы серверов. Поддерживается только vless,
    остальное помечается невалидным с объяснением."""
    out: list[dict] = []
    for line in lines:
        scheme = line.split("://", 1)[0].lower() if "://" in line else ""
        if scheme != "vless":
            out.append({
                "vless_url": "",
                "name": line[:80],
                "server": "",
                "port": None,
                "transport": "",
                "valid": False,
                "error": f"схема '{scheme or '?'}' не поддерживается (только vless)",
            })
            continue
        try:
            p = parse_vless_url(line)
            out.append({
                "vless_url": line,
                "name": p.remark or f"{p.server}:{p.port}",
                "server": p.server,
                "port": p.port,
                "transport": p.transport,
                "valid": True,
                "error": None,
            })
        except VlessParseError as e:
            msg = str(e)
            if "pbk" in msg:
                # В ссылке нет ключей Reality — такой сервер Xray не потянет.
                msg = "в ссылке нет ключей Reality (pbk/sid) — сервер не поддерживается"
            out.append({
                "vless_url": line,
                "name": unquote(line.rsplit("#", 1)[-1] if "#" in line else line)[:80],
                "server": "",
                "port": None,
                "transport": "",
                "valid": False,
                "error": msg,
            })
    return out


async def fetch_subscription(url: str, timeout: float = 15.0) -> list[dict]:
    import httpx

    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        trust_env=False,
        headers={"User-Agent": "vless-dashboard/1.0"},
    ) as client:
        r = await client.get(url)
        r.raise_for_status()
        return parse_servers(decode_body(r.text))
