import hashlib

import pytest

from protocol import crypto


def test_udp_key_is_md5_of_public_seed():
    assert crypto.UDP_KEY == hashlib.md5(b"yGAdlopoPVldABfn").digest()
    assert len(crypto.UDP_KEY) == 16


def test_normalise_key_length():
    assert crypto.normalise_key("0123456789abcdef") == b"0123456789abcdef"
    with pytest.raises(ValueError):
        crypto.normalise_key("too-short")


def test_ecb_round_trip():
    key = b"0123456789abcdef"
    for text in (b"{}", b'{"dps":{"1":true}}', b"x" * 47):
        assert crypto.decrypt_ecb(key, crypto.encrypt_ecb(key, text)) == text


def test_ecb_block_is_deterministic_and_unpadded():
    key = b"A" * 16
    block = b"B" * 16
    out = crypto.encrypt_ecb_block(key, block)
    assert len(out) == 16
    assert crypto.encrypt_ecb_block(key, block) == out
    with pytest.raises(ValueError):
        crypto.encrypt_ecb_block(key, b"short")


def test_gcm_round_trip_with_aad():
    key = b"0123456789abcdef"
    nonce = b"n" * 12
    aad = b"header-bytes"
    ct, tag = crypto.encrypt_gcm(key, nonce, b'{"ok":1}', aad)
    assert crypto.decrypt_gcm(key, nonce, ct, tag, aad) == b'{"ok":1}'
    with pytest.raises(Exception):
        crypto.decrypt_gcm(key, nonce, ct, tag, b"wrong-aad")
