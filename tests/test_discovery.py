import json

from protocol import message as M
from protocol.crypto import UDP_KEY, encrypt_ecb
from protocol.discovery import decrypt_broadcast, to_device

ANNOUNCE = {
    "ip": "192.168.1.50",
    "gwId": "bf99887766554433221100",
    "version": "3.3",
    "productKey": "abcd1234efgh5678",
    "encrypt": True,
}


def test_plaintext_31_broadcast():
    payload = decrypt_broadcast(json.dumps(ANNOUNCE).encode())
    assert payload["gwId"] == ANNOUNCE["gwId"]
    dev = to_device(payload)
    assert dev.address == "192.168.1.50"
    assert dev.version == "3.3"
    assert dev.product_key == "abcd1234efgh5678"


def test_ecb_33_broadcast_whole_datagram():
    datagram = encrypt_ecb(UDP_KEY, json.dumps(ANNOUNCE).encode())
    payload = decrypt_broadcast(datagram)
    assert payload and payload["ip"] == "192.168.1.50"


def test_framed_encrypted_broadcast():
    body = encrypt_ecb(UDP_KEY, json.dumps(ANNOUNCE).encode())
    frame = M.pack(0, 0x13, b"\x00\x00\x00\x00" + body, key=UDP_KEY)
    payload = decrypt_broadcast(frame)
    assert payload and payload["gwId"] == ANNOUNCE["gwId"]


def test_junk_returns_none():
    assert decrypt_broadcast(b"\xff\xff\xff\xff not a tuya packet") is None
