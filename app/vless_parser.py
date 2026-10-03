"""VLESS URL parser — Python-порт entrypoint.sh из VLESS-to-HTTP."""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse, parse_qs, unquote


class VlessParseError(ValueError):
    pass


@dataclass
class VlessParams:
    user_id: str
    server: str
    port: int
    pubkey: str
    sni: str
    sid: str
    fp: str = "firefox"
    spx: str = "/"
    flow: str = ""
    transport: str = "tcp"  # tcp | xhttp
    path: str = ""
    host: str = ""
    mode: str = ""
    remark: str = ""


def _first(qs: dict, key: str) -> str:
    vals = qs.get(key)
    if not vals:
        return ""
    return vals[0]


def parse_vless_url(raw: str) -> VlessParams:
    # strip CR/LF, cut trailing comment after # (как в entrypoint.sh, но
    # оставляем URL-фрагмент? в vless-ссылках # = имя, поэтому сначала
    # отрезаем только если это комментарий вида " # ..." — проще: если
    # строка содержит пробел+#, режем. Иначе пробуем парсить целиком,
    # urlparse сам положит имя во fragment и оно не помешает.)
    s = raw.replace("\r", "").replace("\n", "").strip()
    if not s:
        raise VlessParseError("пустая VLESS-ссылка")
    if " #" in s:
        s = s.split(" #", 1)[0].strip()
    if not s.startswith("vless://"):
        raise VlessParseError("ссылка должна начинаться с vless://")

    try:
        u = urlparse(s)
    except Exception as e:
        raise VlessParseError(f"некорректный URL: {e}")

    user_id = unquote(u.username or "")
    server = u.hostname or ""
    port = u.port or 0
    qs = parse_qs(u.query or "")

    pubkey = _first(qs, "pbk")
    sni = _first(qs, "sni")
    fp = _first(qs, "fp") or "firefox"
    sid = _first(qs, "sid")
    spx = unquote(_first(qs, "spx") or "/")
    flow = _first(qs, "flow")
    transport = _first(qs, "type") or "tcp"
    path = unquote(_first(qs, "path"))
    # host может содержать запятые, закодированные как %2C
    host = unquote(_first(qs, "host"))
    mode = _first(qs, "mode")
    remark = unquote(u.fragment or "").strip()

    if not user_id:
        raise VlessParseError("пустой USER_ID (uuid)")
    if not server:
        raise VlessParseError("пустой SERVER (хост)")
    if not port:
        raise VlessParseError("пустой PORT")
    if not pubkey:
        raise VlessParseError("пустой pbk (public key)")
    if not sni:
        raise VlessParseError("пустой sni")
    if not sid:
        raise VlessParseError("пустой sid (short id)")
    if transport not in ("tcp", "xhttp"):
        raise VlessParseError(
            f"неподдерживаемый transport '{transport}' (доступны: tcp, xhttp)"
        )
    if transport == "xhttp" and not path:
        raise VlessParseError("пустой path для xhttp-транспорта")

    return VlessParams(
        user_id=user_id,
        server=server,
        port=int(port),
        pubkey=pubkey,
        sni=sni,
        sid=sid,
        fp=fp,
        spx=spx,
        flow=flow,
        transport=transport,
        path=path,
        host=host,
        mode=mode,
        remark=remark,
    )


def build_xray_config(params: VlessParams, socks_port: int | None, http_port: int | None) -> dict:
    """Собирает config.json для одного профиля (один Xray-процесс)."""
    inbounds: list[dict] = []
    if http_port:
        inbounds.append(
            {
                "port": http_port,
                "protocol": "http",
                "listen": "0.0.0.0",
                "settings": {"allowTransparent": True, "timeout": 300},
                "sniffing": {"enabled": True, "destOverride": ["http", "tls"]},
            }
        )
    if socks_port:
        inbounds.append(
            {
                "port": socks_port,
                "protocol": "socks",
                "listen": "0.0.0.0",
                "settings": {"auth": "noauth", "udp": True},
            }
        )
    if not inbounds:
        raise VlessParseError("нужен хотя бы один порт (socks или http)")

    user: dict = {"id": params.user_id, "encryption": "none", "level": 0}
    if params.flow:
        user["flow"] = params.flow

    if params.transport == "xhttp":
        xhttp: dict = {"path": params.path}
        if params.host:
            xhttp["host"] = params.host
        if params.mode:
            xhttp["mode"] = params.mode
        stream = {
            "network": "xhttp",
            "security": "reality",
            "realitySettings": {
                "show": False,
                "publicKey": params.pubkey,
                "shortId": params.sid,
                "spiderX": params.spx,
                "fingerprint": params.fp,
                "serverName": params.sni,
            },
            "xhttpSettings": xhttp,
        }
    else:
        stream = {
            "network": "tcp",
            "security": "reality",
            "realitySettings": {
                "show": False,
                "publicKey": params.pubkey,
                "shortId": params.sid,
                "spiderX": params.spx,
                "fingerprint": params.fp,
                "serverName": params.sni,
            },
        }

    return {
        "log": {"loglevel": "warning"},
        "inbounds": inbounds,
        "outbounds": [
            {
                "protocol": "vless",
                "settings": {
                    "vnext": [
                        {
                            "address": params.server,
                            "port": params.port,
                            "users": [user],
                        }
                    ]
                },
                "streamSettings": stream,
                "tag": "proxy",
            },
            {"protocol": "freedom", "settings": {}, "tag": "direct"},
        ],
    }
