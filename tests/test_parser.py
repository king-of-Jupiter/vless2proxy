import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.vless_parser import parse_vless_url, build_xray_config, VlessParseError

TCP_URL = (
    "vless://49b4b82b-73f0-4772-86ca-ca5059375c63@45.127.127.127:443"
    "?security=reality&encryption=none&pbk=6ECfTRNxRBiv7GLIIwOhwlkDs9NyYoZ7lHZrWeU1Q"
    "&fp=firefox&sni=github.com&sid=c8aa6a68a476c885&spx=/&flow=xtls-rprx-vision"
)
XHTTP_URL = (
    "vless://49b4b82b-73f0-4772-86ca-ca5059375c63@45.127.127.127:443"
    "?security=reality&encryption=none&type=xhttp&path=%2Fmy-path&host=example.com"
    "&sni=example.com&pbk=6ECfTRNxRBiv7GLIIwOhwlkDs9NyYoZ7lHZrWeU1Q"
    "&sid=c8aa6a68a476c885&fp=chrome&mode=auto"
)

failures = []


def check(name, fn):
    try:
        fn()
        print(f"PASS {name}")
    except Exception as e:
        failures.append(name)
        print(f"FAIL {name}: {e}")


def t_tcp():
    p = parse_vless_url(TCP_URL)
    assert p.transport == "tcp", p.transport
    assert p.server == "45.127.127.127"
    assert p.port == 443
    assert p.flow == "xtls-rprx-vision"
    cfg = build_xray_config(p, socks_port=1080, http_port=None)
    assert cfg["inbounds"][0]["protocol"] == "socks"
    assert cfg["outbounds"][0]["streamSettings"]["network"] == "tcp"


def t_xhttp():
    p = parse_vless_url(XHTTP_URL)
    assert p.transport == "xhttp", p.transport
    assert p.path == "/my-path", p.path
    assert p.host == "example.com"
    assert p.mode == "auto"
    cfg = build_xray_config(p, socks_port=1081, http_port=9001)
    assert len(cfg["inbounds"]) == 2
    assert cfg["outbounds"][0]["streamSettings"]["xhttpSettings"]["path"] == "/my-path"


def t_xhttp_no_path():
    bad = XHTTP_URL.replace("path=%2Fmy-path&", "")
    try:
        parse_vless_url(bad)
    except VlessParseError:
        return
    raise AssertionError("ожидалась ошибка empty path")


def t_defaults():
    minimal = (
        "vless://uuid-1234@1.2.3.4:443?security=reality&encryption=none"
        "&pbk=PK&sni=example.com&sid=SID"
    )
    p = parse_vless_url(minimal)
    assert p.transport == "tcp"
    assert p.fp == "firefox"
    assert p.spx == "/"


check("tcp", t_tcp)
check("xhttp", t_xhttp)
check("xhttp_no_path_rejected", t_xhttp_no_path)
check("defaults", t_defaults)

if failures:
    print(f"\n{len(failures)} FAILED: {failures}")
    sys.exit(1)
print("\nAll parser tests passed")
