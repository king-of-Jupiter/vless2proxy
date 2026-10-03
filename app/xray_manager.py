"""Управление Xray-процессами: по одному процессу на профиль."""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

from .vless_parser import parse_vless_url, build_xray_config, VlessParseError

DATA_DIR = os.environ.get("DATA_DIR", str(Path(__file__).resolve().parents[1] / "data"))
CONFIG_DIR = os.path.join(DATA_DIR, "configs")
LOG_DIR = os.path.join(DATA_DIR, "logs")
XRAY_BIN = os.environ.get("XRAY_BIN") or shutil.which("Xray") or shutil.which("xray") or "/usr/local/bin/Xray"

_processes: dict[int, subprocess.Popen] = {}


def ensure_dirs() -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)


def config_path(pid: int) -> str:
    return os.path.join(CONFIG_DIR, f"config-{pid}.json")


def log_path(pid: int) -> str:
    return os.path.join(LOG_DIR, f"xray-{pid}.log")


def is_running(pid: int) -> bool:
    p = _processes.get(pid)
    return p is not None and p.poll() is None


def port_free(port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        s.bind(("0.0.0.0", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def write_config(profile: dict) -> str:
    params = parse_vless_url(profile["vless_url"])
    cfg = build_xray_config(params, profile.get("socks_port"), profile.get("http_port"))
    ensure_dirs()
    path = config_path(profile["id"])
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    return path


def start(profile: dict) -> None:
    """Запускает (или перезапускает) Xray для профиля."""
    stop(profile["id"])
    cfg_path = write_config(profile)
    ensure_dirs()
    if not (os.path.isfile(XRAY_BIN) or shutil.which(XRAY_BIN)):
        raise RuntimeError(f"Xray не найден: {XRAY_BIN}")
    logf = open(log_path(profile["id"]), "a", encoding="utf-8")
    logf.write(f"\n===== START {time.strftime('%Y-%m-%d %H:%M:%S')} pid={profile['id']} =====\n")
    logf.flush()
    proc = subprocess.Popen(
        [XRAY_BIN, "run", "-config", cfg_path],
        stdout=logf,
        stderr=subprocess.STDOUT,
    )
    _processes[profile["id"]] = proc


def stop(pid: int) -> None:
    p = _processes.pop(pid, None)
    if p is None:
        return
    try:
        p.terminate()
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
    except Exception:
        pass


def tail_logs(pid: int, n: int = 100) -> str:
    path = log_path(pid)
    if not os.path.isfile(path):
        return ""
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        block = 4096
        data = b""
        while len(data.splitlines()) <= n and size > 0:
            step = min(block, size)
            size -= step
            f.seek(size)
            data = f.read() + data
            if size == 0:
                break
    lines = data.decode("utf-8", errors="replace").splitlines()
    return "\n".join(lines[-n:])
