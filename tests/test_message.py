"""Framing round-trips for the 55AA (CRC + HMAC) and 6699 (GCM) formats.

Device -> client frames always carry a 4-byte return code in front of the
payload, so the tests prepend it before packing and expect it stripped back off.
"""

import struct

from protocol import message as M

KEY = b"0123456789abcdef"
RET0 = b"\x00\x00\x00\x00"


def _device_frame(cmd, payload, **kw):
    return M.pack(1, cmd, RET0 + payload, key=KEY, **kw)


def test_crc_frame_round_trip():
    frame = _device_frame(M.STATUS, b'{"dps":{"1":true}}')
    msgs, leftover = M.unpack_stream(frame, key=KEY, use_hmac=False)
    assert leftover == b""
    assert len(msgs) == 1
    m = msgs[0]
    assert m.cmd == M.STATUS
    assert m.checksum_ok is True
    assert m.payload == b'{"dps":{"1":true}}'


def test_hmac_frame_round_trip():
    frame = _device_frame(M.DP_QUERY, b"ciphertext-stand-in", use_hmac=True)
    msgs, _ = M.unpack_stream(frame, key=KEY, use_hmac=True)
    assert msgs[0].payload == b"ciphertext-stand-in"
    assert msgs[0].checksum_ok is True


def test_hmac_frame_detects_tampering():
    frame = bytearray(_device_frame(M.DP_QUERY, b"abcdefabcdef", use_hmac=True))
    frame[20] ^= 0x01
    msgs, _ = M.unpack_stream(bytes(frame), key=KEY, use_hmac=True)
    assert msgs[0].checksum_ok is False


def test_gcm_frame_round_trip_strips_retcode():
    # 6699 keeps the retcode inside the plaintext; strip only when JSON follows.
    frame = M.pack(
        7,
        M.CONTROL_NEW,
        RET0 + b'{"dps":{"1":false}}',
        key=KEY,
        use_gcm=True,
        nonce=b"z" * 12,
    )
    msgs, leftover = M.unpack_stream(frame, key=KEY, use_hmac=False)
    assert leftover == b""
    assert msgs[0].payload == b'{"dps":{"1":false}}'
    assert msgs[0].retcode == 0


def test_two_frames_and_a_partial_in_one_buffer():
    a = _device_frame(M.STATUS, b'{"a":1}')
    b = _device_frame(M.STATUS, b'{"b":2}')
    buf = a + b + b"\x00\x00\x55\xaa\x00\x00"  # dangling header start
    msgs, leftover = M.unpack_stream(buf, key=KEY, use_hmac=False)
    assert [m.payload for m in msgs] == [b'{"a":1}', b'{"b":2}']
    assert leftover.startswith(b"\x00\x00\x55\xaa")


def test_garbage_prefix_is_skipped():
    frame = b"noise-noise" + _device_frame(M.STATUS, b"{}")
    msgs, _ = M.unpack_stream(frame, key=KEY, use_hmac=False)
    assert msgs and msgs[0].payload == b"{}"


def test_header_lengths_match_reference():
    assert M._HDR_55AA.size == 16
    assert M._HDR_6699.size == 18
    assert struct.calcsize(">32sI") == 36
