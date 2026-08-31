#!/usr/bin/env python3
"""Standalone Tuya-LAN helper — no Home Assistant required.

    python tools/tuya_lan_probe.py discover [--timeout 10]
    python tools/tuya_lan_probe.py dump  <ip> <device_id> <local_key> [--version 3.3]
    python tools/tuya_lan_probe.py set   <ip> <device_id> <local_key> <dp> <value> [--version 3.3]
    python tools/tuya_lan_probe.py extract-keys <path-to-unpacked-android-backup>

Only depends on `cryptography` (`pip install cryptography`).
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import json
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "custom_components" / "tuya_lan"))

from protocol import TuyaDevice  # noqa: E402
from protocol.discovery import scan  # noqa: E402


def _coerce(value: str):
    try:
        return ast.literal_eval(value)
    except (ValueError, SyntaxError):
        return value


async def _dump(args: argparse.Namespace) -> None:
    dev = TuyaDevice(args.device_id, args.ip, args.local_key, args.version)
    try:
        await dev.connect()
        print(json.dumps(await dev.status(), indent=2, ensure_ascii=False))
    finally:
        await dev.close()


async def _set(args: argparse.Namespace) -> None:
    dev = TuyaDevice(args.device_id, args.ip, args.local_key, args.version)
    try:
        await dev.connect()
        print(json.dumps(await dev.set_dp(args.dp, _coerce(args.value)), indent=2, ensure_ascii=False))
    finally:
        await dev.close()


async def _discover(args: argparse.Namespace) -> None:
    devices = await scan(args.timeout)
    for dev in sorted(devices.values(), key=lambda d: d.address):
        print(f"{dev.address:15}  {dev.device_id}  v{dev.version}  key_needed={dev.encrypted}")
    if not devices:
        print("(nothing heard - are you on the same L2 network as the devices?)")


_KEY_RE = re.compile(r'"?(?:localKey|local_key)"?\s*[:=]\s*"([A-Za-z0-9+/=]{16,24})"')


def _extract_keys(args: argparse.Namespace) -> None:
    root = Path(args.path)
    found: dict[str, str] = {}
    for path in root.rglob("*"):
        if not path.is_file() or path.stat().st_size > 20_000_000:
            continue
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        for m in _KEY_RE.finditer(text):
            ctx = text[max(0, m.start() - 400) : m.start()]
            did = re.search(r'"(?:devId|id|uuid)"\s*:\s*"([a-z0-9]{16,25})"', ctx)
            found[did.group(1) if did else f"?{len(found)}"] = m.group(1)
    print(json.dumps(found, indent=2))
    print(f"\n{len(found)} key(s) found", file=sys.stderr)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("discover")
    d.add_argument("--timeout", type=float, default=10.0)
    d.set_defaults(func=lambda a: asyncio.run(_discover(a)))

    for name, fn in (("dump", _dump), ("set", _set)):
        s = sub.add_parser(name)
        s.add_argument("ip")
        s.add_argument("device_id")
        s.add_argument("local_key")
        if name == "set":
            s.add_argument("dp")
            s.add_argument("value")
        s.add_argument("--version", default="3.3")
        s.set_defaults(func=lambda a, fn=fn: asyncio.run(fn(a)))

    e = sub.add_parser("extract-keys")
    e.add_argument("path")
    e.set_defaults(func=_extract_keys)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
