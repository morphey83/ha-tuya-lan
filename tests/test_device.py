import json

import pytest

from protocol import crypto
from protocol.device import TuyaDevice, _extract_dps
from protocol.version import ProtocolVersion

KEY = "0123456789abcdef"
KEYB = b"0123456789abcdef"
DID = "bf00000000000000000001"


def _dev(version):
    return TuyaDevice(DID, "10.0.0.9", KEY, version)


def test_version_parsing_and_flags():
    assert ProtocolVersion.parse("v3.3") is ProtocolVersion.V33
    assert ProtocolVersion.parse(3.4) is ProtocolVersion.V34
    assert ProtocolVersion.V35.uses_gcm and ProtocolVersion.V35.needs_session
    assert ProtocolVersion.V34.uses_hmac and not ProtocolVersion.V34.uses_gcm
    assert not ProtocolVersion.V33.needs_session
    assert ProtocolVersion.V33.header == b"3.3" + b"\x00" * 12


def test_build_command_dp_query_v33():
    _real_cmd, payload = _dev("3.3")._build_command(10, dps=None, dp_ids=None)
    body = json.loads(payload)
    assert set(body) == {"gwId", "devId", "uid", "t"}
    assert body["devId"] == DID


def test_build_command_control_v34_uses_protocol_5_envelope():
    from protocol import message as M

    real_cmd, payload = _dev("3.4")._build_command(M.CONTROL, dps={"1": True}, dp_ids=None)
    assert real_cmd == M.CONTROL_NEW
    body = json.loads(payload)
    assert body["protocol"] == 5
    assert body["data"]["dps"] == {"1": True}


@pytest.mark.parametrize("with_header", [False, True])
def test_decode_payload_v33(with_header):
    dev = _dev("3.3")
    enc = crypto.encrypt_ecb(KEYB, b'{"dps":{"1":true,"9":0}}')
    if with_header:
        enc = b"3.3" + b"\x00" * 12 + enc
    assert _extract_dps(dev._decode_payload(enc)) == {"1": True, "9": 0}


def test_decode_payload_v34_whole_body_encrypted():
    dev = _dev("3.4")
    dev._active_key = KEYB  # pretend the session key was negotiated
    plain = b"3.4" + b"\x00" * 12 + b'{"data":{"dps":{"2":42}}}'
    enc = crypto.encrypt_ecb(KEYB, plain)
    assert _extract_dps(dev._decode_payload(enc)) == {"2": 42}


def test_decode_payload_v35_is_already_plaintext():
    dev = _dev("3.5")
    payload = b"3.5" + b"\x00" * 12 + b'{"dps":{"20":1000}}'
    assert _extract_dps(dev._decode_payload(payload)) == {"20": 1000}


def test_decode_payload_rejects_non_json():
    with pytest.raises(Exception):
        _dev("3.3")._decode_payload(crypto.encrypt_ecb(KEYB, b"not-json-at-all"))
