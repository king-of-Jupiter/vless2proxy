"""SQLite-слой: profiles + проверка портов."""
from __future__ import annotations

import aiosqlite
import os
import time

DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "data"))
DB_PATH = os.path.join(DATA_DIR, "profiles.db")
SOCKS_BASE_PORT = int(os.environ.get("SOCKS_BASE_PORT", "1080"))
HTTP_BASE_PORT = int(os.environ.get("HTTP_BASE_PORT", "9000"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  vless_url TEXT NOT NULL,
  mode TEXT NOT NULL DEFAULT 'socks5',
  socks_port INTEGER,
  http_port INTEGER,
  enabled INTEGER NOT NULL DEFAULT 1,
  last_status TEXT DEFAULT 'unknown',
  last_ping_ms INTEGER,
  last_ip TEXT,
  last_check_at REAL,
  last_error TEXT,
  created_at REAL NOT NULL
);
"""


async def init_db() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()


def row_to_dict(row: aiosqlite.Row) -> dict:
    return {
        "id": row[0],
        "name": row[1],
        "vless_url": row[2],
        "mode": row[3],
        "socks_port": row[4],
        "http_port": row[5],
        "enabled": bool(row[6]),
        "last_status": row[7] or "unknown",
        "last_ping_ms": row[8],
        "last_ip": row[9],
        "last_check_at": row[10],
        "last_error": row[11],
        "created_at": row[12],
    }


async def list_profiles() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id,name,vless_url,mode,socks_port,http_port,enabled,"
            "last_status,last_ping_ms,last_ip,last_check_at,last_error,created_at"
            " FROM profiles ORDER BY id"
        )
        rows = await cur.fetchall()
        return [row_to_dict(r) for r in rows]


async def get_profile(pid: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id,name,vless_url,mode,socks_port,http_port,enabled,"
            "last_status,last_ping_ms,last_ip,last_check_at,last_error,created_at"
            " FROM profiles WHERE id=?",
            (pid,),
        )
        r = await cur.fetchone()
        return row_to_dict(r) if r else None


async def create_profile(name, vless_url, mode, socks_port, http_port) -> dict:
    now = time.time()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO profiles (name,vless_url,mode,socks_port,http_port,enabled,created_at)"
            " VALUES (?,?,?,?,?,1,?)",
            (name, vless_url, mode, socks_port, http_port, now),
        )
        await db.commit()
        pid = cur.lastrowid
    return await get_profile(pid)


async def update_profile(pid: int, fields: dict) -> dict | None:
    allowed = {"name", "vless_url", "mode", "socks_port", "http_port", "enabled"}
    sets = [(k, v) for k, v in fields.items() if k in allowed]
    if sets:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                f"UPDATE profiles SET {', '.join(f'{k}=?' for k, _ in sets)} WHERE id=?",
                tuple(v for _, v in sets) + (pid,),
            )
            await db.commit()
    return await get_profile(pid)


async def delete_profile(pid: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM profiles WHERE id=?", (pid,))
        await db.commit()


async def update_health(pid: int, status: str, ping_ms: int | None, ip: str | None, error: str | None) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE profiles SET last_status=?,last_ping_ms=?,last_ip=?,"
            "last_check_at=?,last_error=? WHERE id=?",
            (status, ping_ms, ip, time.time(), error, pid),
        )
        await db.commit()


async def next_ports() -> dict:
    """Следующие свободные порты: max+1 (старт с SOCKS_BASE_PORT / HTTP_BASE_PORT)."""
    profiles = await list_profiles()
    socks = [p["socks_port"] for p in profiles if p["socks_port"]]
    https = [p["http_port"] for p in profiles if p["http_port"]]
    return {
        "socks_port": (max(socks) + 1) if socks else SOCKS_BASE_PORT,
        "http_port": (max(https) + 1) if https else HTTP_BASE_PORT,
    }


async def port_taken(port: int, exclude_id: int | None = None) -> bool:
    profiles = await list_profiles()
    for p in profiles:
        if exclude_id is not None and p["id"] == exclude_id:
            continue
        if p["socks_port"] == port or p["http_port"] == port:
            return True
    return False
