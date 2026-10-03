import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.subscription import decode_body, parse_servers

TCP_LINE = (
    "vless://49b4b82b-73f0-4772-86ca-ca5059375c63@10.0.0.1:443"
    "?security=reality&encryption=none&pbk=PK&fp=firefox&sni=example.com"
    "&sid=SID&spx=/&flow=xtls-rprx-vision#test-tcp"
)
XHTTP_LINE = (
    "vless://49b4b82b-73f0-4772-86ca-ca5059375c63@10.0.0.2:443"
    "?security=reality&encryption=none&type=xhttp&path=%2Fp&sni=example.com"
    "&pbk=PK&sid=SID&fp=chrome#test-xhttp"
)

failures = []


def check(name, fn):
    try:
        fn()
        print(f"PASS {name}")
    except Exception as e:
        failures.append(name)
        print(f"FAIL {name}: {e}")


def t_base64_single_line():
    blob = base64.b64encode(f"{TCP_LINE}\n{XHTTP_LINE}\n".encode()).decode()
    lines = decode_body(blob)
    assert len(lines) == 2, lines
    assert lines[0].startswith("vless://")


def t_plain_multiline():
    lines = decode_body(f"{TCP_LINE}\n\n{XHTTP_LINE}\n")
    assert len(lines) == 2, lines


def t_empty():
    assert decode_body("   \n  ") == []


def t_parse_mixed():
    servers = parse_servers([TCP_LINE, XHTTP_LINE, "vmess://eyJhZGQiOiIxIn0=", "мусор"])
    assert len(servers) == 4
    assert servers[0]["valid"] and servers[0]["transport"] == "tcp"
    assert servers[0]["name"] == "test-tcp"
    assert servers[1]["valid"] and servers[1]["transport"] == "xhttp"
    assert not servers[2]["valid"] and "только vless" in servers[2]["error"]
    assert not servers[3]["valid"]


def t_parse_broken_vless():
    servers = parse_servers(["vless://nope"])
    assert len(servers) == 1 and not servers[0]["valid"]


def t_no_reality_keys_friendly():
    no_keys = (
        "vless://49b4b82b-73f0-4772-86ca-ca5059375c63@10.0.0.3:443"
        "?security=reality&encryption=none&type=xhttp&path=%2Fp&sni=example.com#%F0%9F%87%AB%F0%9F%87%AE%20finland"
    )
    servers = parse_servers([no_keys])
    assert len(servers) == 1 and not servers[0]["valid"]
    assert "не поддерживается" in servers[0]["error"]
    assert "%F0" not in servers[0]["name"]  # remark декодирован


check("base64_single_line", t_base64_single_line)
check("plain_multiline", t_plain_multiline)
check("empty", t_empty)
check("parse_mixed", t_parse_mixed)
check("parse_broken_vless", t_parse_broken_vless)
check("no_reality_keys_friendly", t_no_reality_keys_friendly)

if failures:
    print(f"\n{len(failures)} FAILED: {failures}")
    sys.exit(1)
print("\nAll subscription tests passed")
