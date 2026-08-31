"""AES primitives used by the Tuya LAN protocol.

* v3.1 - v3.4 use AES-128-ECB with PKCS#7 padding.
* v3.5 uses AES-128-GCM with a 12-byte nonce and 16-byte tag, with the frame
  header (minus the 4-byte magic prefix) as additional authenticated data.

Only :mod:`cryptography` is required (already a Home Assistant dependency).
"""

from __future__ import annotations

import hashlib

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# The broadcast/UDP key has been public for years (originally via tuya-convert).
UDP_KEY = hashlib.md5(b"yGAdlopoPVldABfn").digest()


def normalise_key(key: str | bytes) -> bytes:
    """Return a 16-byte AES key from a local key string."""
    raw = key.encode("latin1") if isinstance(key, str) else bytes(key)
    if len(raw) != 16:
        raise ValueError(f"Tuya local key must be 16 bytes, got {len(raw)}")
    return raw


def _pkcs7_pad(data: bytes, block: int = 16) -> bytes:
    pad = block - (len(data) % block)
    return data + bytes([pad]) * pad


def _pkcs7_unpad(data: bytes) -> bytes:
    if not data:
        return data
    pad = data[-1]
    if pad < 1 or pad > 16 or pad > len(data):
        # Not padded (some firmware returns raw JSON) - hand it back untouched.
        return data
    return data[:-pad]


def encrypt_ecb(key: bytes, plaintext: bytes) -> bytes:
    encryptor = Cipher(algorithms.AES(key), modes.ECB()).encryptor()  # noqa: S305
    return encryptor.update(_pkcs7_pad(plaintext)) + encryptor.finalize()


def decrypt_ecb(key: bytes, ciphertext: bytes) -> bytes:
    if len(ciphertext) % 16:
        raise ValueError("ECB ciphertext length is not a multiple of 16")
    decryptor = Cipher(algorithms.AES(key), modes.ECB()).decryptor()  # noqa: S305
    return _pkcs7_unpad(decryptor.update(ciphertext) + decryptor.finalize())


def encrypt_ecb_block(key: bytes, block16: bytes) -> bytes:
    """Encrypt exactly one 16-byte block with AES-ECB and no padding.

    Used to derive the v3.4 session key.
    """
    if len(block16) != 16:
        raise ValueError("block must be exactly 16 bytes")
    encryptor = Cipher(algorithms.AES(key), modes.ECB()).encryptor()  # noqa: S305
    return encryptor.update(block16) + encryptor.finalize()


def encrypt_gcm(key: bytes, nonce: bytes, plaintext: bytes, aad: bytes) -> tuple[bytes, bytes]:
    """Return ``(ciphertext, tag)``."""
    combined = AESGCM(key).encrypt(nonce, plaintext, aad)
    return combined[:-16], combined[-16:]


def decrypt_gcm(key: bytes, nonce: bytes, ciphertext: bytes, tag: bytes, aad: bytes) -> bytes:
    return AESGCM(key).decrypt(nonce, ciphertext + tag, aad)
