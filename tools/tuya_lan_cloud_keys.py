#!/usr/bin/env python3
"""One-time helper: pull local keys for your own Tuya devices from the
Tuya IoT Platform (https://iot.tuya.com).

This is the ONLY step that talks to a Tuya server, it reads only your own
account, and you never need to run it again - once you have the keys, the
integration is 100% local.

Prerequisites (see docs/getting-keys.md for screenshots):
  1. iot.tuya.com -> Cloud -> Development -> create a project
     (Development method: "Smart Home", pick your data-center region).
  2. In the project: "Devices" -> "Link App Account" -> scan the QR code with
     the Smart Life / Tuya app ("Me" -> top-right scan icon).
  3. Project overview -> copy "Access ID/Client ID" and "Access Secret/Client
     Secret".
  4. Project -> "Service API" -> make sure "IoT Core" is authorized.

Usage:
  python tools/tuya_lan_cloud_keys.py --region eu --client-id xxxx --client-secret yyyy
  python tools/tuya_lan_cloud_keys.py --region eu --client-id xxxx --client-secret yyyy --json

Regions: us  eu  cn  in  us-e  eu-w  sg   (match your project's data center)

Only the Python standard library is required.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import sys
import time
import urllib.error
import urllib.request

_HOSTS = {
    "us": "openapi.tuyaus.com",
    "az": "openapi.tuyaus.com",
    "us-e": "openapi-ueaz.tuyaus.com",
    "ue": "openapi-ueaz.tuyaus.com",
    "eu": "openapi.tuyaeu.com",
    "eu-w": "openapi-weaz.tuyaeu.com",
    "we": "openapi-weaz.tuyaeu.com",
    "cn": "openapi.tuyacn.com",
    "in": "openapi.tuyain.com",
    "sg": "openapi-sg.tuyaus.com",
}


class TuyaCloud:
    def __init__(self, region: str, client_id: str, secret: str) -> None:
        self.host = _HOSTS.get(region.lower())
        if not self.host:
            raise SystemExit(f"unknown region {region!r}; choose from {', '.join(_HOSTS)}")
        self.client_id = client_id
        self.secret = secret.encode()
        self.token: str | None = None

    def _sign(self, method: str, path_with_query: str, body: str, now: str) -> str:
        payload = self.client_id + (self.token or "") + now
        content_sha = hashlib.sha256(body.encode()).hexdigest()
        payload += f"{method}\n{content_sha}\n\n/{path_with_query.lstrip('/')}"
        return hmac.new(self.secret, payload.encode(), hashlib.sha256).hexdigest().upper()

    def _request(self, path: str, query: dict[str, str] | None = None) -> dict:
        method = "GET"
        qs = ""
        if query:
            qs = "&".join(f"{k}={query[k]}" for k in sorted(query))
        full_path = f"v1.0/{path}" + (f"?{qs}" if qs else "")
        now = str(int(time.time() * 1000))
        headers = {
            "client_id": self.client_id,
            "sign": self._sign(method, full_path, "", now),
            "t": now,
            "sign_method": "HMAC-SHA256",
        }
        if self.token:
            headers["access_token"] = self.token
        else:
            headers["secret"] = self.secret.decode()
        req = urllib.request.Request(f"https://{self.host}/{full_path}", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:  # https URL, fixed host
                data = json.loads(resp.read())
        except urllib.error.HTTPError as err:
            raise SystemExit(f"HTTP {err.code}: {err.read().decode(errors='replace')}") from err
        if not data.get("success"):
            raise SystemExit(f"Tuya API error {data.get('code')}: {data.get('msg')}")
        return data["result"]

    def get_token(self) -> None:
        self.token = self._request("token?grant_type=1")["access_token"]

    def devices(self) -> list[dict]:
        out: list[dict] = []
        query = {"size": "50"}
        while True:
            result = self._request("iot-01/associated-users/devices", query)
            out.extend(result.get("devices", []))
            if not result.get("has_more"):
                break
            # Note: last_row_key is used verbatim for both signing and the
            # request URL. If you have >50 devices and it contains characters
            # that need URL-encoding this may need adjusting - rare.
            query["last_row_key"] = result["last_row_key"]
        return out


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--region", required=True)
    ap.add_argument("--client-id", required=True)
    ap.add_argument("--client-secret", required=True)
    ap.add_argument("--json", action="store_true", help="dump raw device list as JSON")
    args = ap.parse_args()

    cloud = TuyaCloud(args.region, args.client_id, args.client_secret)
    cloud.get_token()
    devices = cloud.devices()
    if not devices:
        sys.exit("No devices. Did you 'Link App Account' in the Tuya project?")

    if args.json:
        print(json.dumps(devices, indent=2, ensure_ascii=False))
        return

    print(f"{'name':<24} {'device_id':<24} {'local_key':<20} {'ip':<15} product_id")
    print("-" * 100)
    for d in devices:
        print(
            f"{(d.get('name') or '')[:23]:<24} "
            f"{d.get('id', ''):<24} "
            f"{d.get('local_key', ''):<20} "
            f"{d.get('ip', ''):<15} "
            f"{d.get('product_id', '')}"
        )
    print(
        "\nNext: add each device in Home Assistant (Tuya-LAN) with its local_key.\n"
        "The protocol version is not in this list - the discovery step in the\n"
        "config flow fills it in, or try 3.3 then 3.4."
    )


if __name__ == "__main__":
    main()
