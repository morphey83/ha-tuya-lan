"""Tuya LAN frame (de)serialisation.

Two wire formats:

* ``0x000055AA ... 0x0000AA55`` for v3.1 - v3.4
  ``prefix(4) seqno(4) cmd(4) length(4) [retcode(4)] payload  crc(4)|hmac(32)  suffix(4)``
* ``0x00006699 ... 0x00009966`` for v3.5 (AES-GCM)
  ``prefix(4) unknown(2) seqno(4) cmd(4) length(4)  nonce(12) ciphertext  tag(16) suffix(4)``
"""

from __future__ import annotations

import binascii
import hmac
import struct
from dataclasses import dataclass
from hashlib import sha256

from .crypto import decrypt_gcm, encrypt_gcm
from .exceptions import TuyaDecodeError

# --- Command types (from Tuya lan_protocol.h) --------------------------------------
AP_CONFIG = 0x01
ACTIVE = 0x02
SESS_KEY_NEG_START = 0x03
SESS_KEY_NEG_RESP = 0x04
SESS_KEY_NEG_FINISH = 0x05
UNBIND = 0x06
CONTROL = 0x07
STATUS = 0x08
HEART_BEAT = 0x09
DP_QUERY = 0x0A
QUERY_WIFI = 0x0B
TOKEN_BIND = 0x0C
CONTROL_NEW = 0x0D
ENABLE_WIFI = 0x0E
DP_QUERY_NEW = 0x10
SCENE_EXECUTE = 0x11
UPDATE_DPS = 0x12
LAN_EXT_STREAM = 0x40

PREFIX_55AA = 0x000055AA
SUFFIX_55AA = 0x0000AA55
PREFIX_6699 = 0x00006699
SUFFIX_6699 = 0x00009966

_HDR_55AA = struct.Struct(">IIII")  # prefix seqno cmd length
_HDR_6699 = struct.Struct(">IHIII")  # prefix unknown seqno cmd length
_RETCODE = struct.Struct(">I")
_END_CRC = struct.Struct(">II")  # crc suffix
_END_HMAC = struct.Struct(">32sI")  # hmac suffix

# Commands whose payload must NOT be prefixed with the 15-byte version header.
NO_HEADER_CMDS = frozenset(
    {
        DP_QUERY,
        DP_QUERY_NEW,
        UPDATE_DPS,
        HEART_BEAT,
        SESS_KEY_NEG_START,
        SESS_KEY_NEG_RESP,
        SESS_KEY_NEG_FINISH,
        LAN_EXT_STREAM,
    }
)

MAX_PAYLOAD = 65536


@dataclass(slots=True)
class TuyaMessage:
    """A decoded frame."""

    seqno: int
    cmd: int
    retcode: int
    payload: bytes
    checksum_ok: bool = True
    prefix: int = PREFIX_55AA


def pack(
    seqno: int,
    cmd: int,
    payload: bytes,
    *,
    key: bytes,
    use_gcm: bool = False,
    use_hmac: bool = False,
    nonce: bytes | None = None,
) -> bytes:
    """Serialise one request frame.

    ``payload`` is the already-encrypted body for 55AA frames, or the plaintext
    body for 6699 frames (this function performs the GCM step).
    """
    if use_gcm:
        assert nonce is not None and len(nonce) == 12
        length = len(payload) + 12 + 16  # nonce + ciphertext + tag
        header = _HDR_6699.pack(PREFIX_6699, 0, seqno, cmd, length)
        aad = header[4:]  # everything after the 4-byte magic
        ciphertext, tag = encrypt_gcm(key, nonce, payload, aad)
        return header + nonce + ciphertext + tag + struct.pack(">I", SUFFIX_6699)

    if use_hmac:
        length = len(payload) + _END_HMAC.size
        head = _HDR_55AA.pack(PREFIX_55AA, seqno, cmd, length) + payload
        digest = hmac.new(key, head, sha256).digest()
        return head + _END_HMAC.pack(digest, SUFFIX_55AA)

    length = len(payload) + _END_CRC.size
    head = _HDR_55AA.pack(PREFIX_55AA, seqno, cmd, length) + payload
    crc = binascii.crc32(head) & 0xFFFFFFFF
    return head + _END_CRC.pack(crc, SUFFIX_55AA)


def _find_frame_start(buffer: bytes) -> int:
    a = buffer.find(b"\x00\x00\x55\xaa")
    b = buffer.find(b"\x00\x00\x66\x99")
    candidates = [i for i in (a, b) if i >= 0]
    return min(candidates) if candidates else -1


def unpack_stream(buffer: bytes, *, key: bytes, use_hmac: bool) -> tuple[list[TuyaMessage], bytes]:
    """Consume as many whole frames as ``buffer`` holds.

    Returns ``(messages, leftover_bytes)``. Never raises on a partial frame.
    """
    messages: list[TuyaMessage] = []
    while True:
        start = _find_frame_start(buffer)
        if start < 0:
            # No frame start yet - keep the last 3 bytes in case a 4-byte magic
            # prefix was split across this read and the next one.
            return messages, buffer[-3:]
        if start > 0:
            buffer = buffer[start:]

        prefix = struct.unpack(">I", buffer[:4])[0]
        if prefix == PREFIX_6699:
            if len(buffer) < _HDR_6699.size:
                return messages, buffer
            _, _, seqno, cmd, length = _HDR_6699.unpack(buffer[: _HDR_6699.size])
            total = _HDR_6699.size + length + 4  # + suffix
        else:
            if len(buffer) < _HDR_55AA.size:
                return messages, buffer
            _, seqno, cmd, length = _HDR_55AA.unpack(buffer[: _HDR_55AA.size])
            total = _HDR_55AA.size + length

        if length <= 0 or length > MAX_PAYLOAD:
            # Corrupt / desynced - drop the magic and resync.
            buffer = buffer[4:]
            continue
        if len(buffer) < total:
            return messages, buffer

        frame, buffer = buffer[:total], buffer[total:]
        try:
            messages.append(_decode_frame(frame, prefix, seqno, cmd, length, key, use_hmac))
        except TuyaDecodeError:
            messages.append(TuyaMessage(seqno, cmd, -1, b"", checksum_ok=False, prefix=prefix))
    # unreachable


def _decode_frame(
    frame: bytes, prefix: int, seqno: int, cmd: int, length: int, key: bytes, use_hmac: bool
) -> TuyaMessage:
    if prefix == PREFIX_6699:
        body = frame[_HDR_6699.size : _HDR_6699.size + length]
        suffix = struct.unpack(">I", frame[-4:])[0]
        if suffix != SUFFIX_6699:
            raise TuyaDecodeError("bad 6699 suffix")
        nonce, ciphertext, tag = body[:12], body[12:-16], body[-16:]
        aad = frame[4 : _HDR_6699.size]
        try:
            plaintext = decrypt_gcm(key, nonce, ciphertext, tag, aad)
        except Exception as err:
            raise TuyaDecodeError(f"GCM auth failed: {err}") from err
        # Unlike 55AA frames, the 4-byte return code on a 6699 frame lives
        # *inside* the GCM plaintext and is not always present (broadcasts and
        # session-negotiation replies omit it), so only strip it when the bytes
        # that follow clearly begin the real payload.
        retcode = 0
        if len(plaintext) >= 5 and plaintext[:1] != b"{" and plaintext[4:5] in (b"{", b"3"):
            retcode = struct.unpack(">I", plaintext[:4])[0]
            plaintext = plaintext[4:]
        return TuyaMessage(seqno, cmd, retcode, plaintext, checksum_ok=True, prefix=prefix)

    # 55AA
    end = _END_HMAC if use_hmac else _END_CRC
    body = frame[_HDR_55AA.size : _HDR_55AA.size + length]
    trailer = body[-end.size :]
    body = body[: -end.size]
    if use_hmac:
        digest, suffix = end.unpack(trailer)
        want = hmac.new(key, frame[: _HDR_55AA.size + length - end.size], sha256).digest()
        checksum_ok = hmac.compare_digest(digest, want)
    else:
        crc, suffix = end.unpack(trailer)
        want = binascii.crc32(frame[: _HDR_55AA.size + length - end.size]) & 0xFFFFFFFF
        checksum_ok = crc == want
    if suffix != SUFFIX_55AA:
        raise TuyaDecodeError("bad 55AA suffix")

    # Every received 55AA frame carries a 4-byte return code before its payload.
    retcode = 0
    if len(body) >= 4:
        retcode = struct.unpack(">I", body[:4])[0]
        body = body[4:]
    return TuyaMessage(seqno, cmd, retcode, body, checksum_ok=checksum_ok, prefix=prefix)
