"""Async client for a single Tuya device on the LAN."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hmac as _hmac
import json
import logging
import os
import time
from collections import deque
from collections.abc import Awaitable, Callable
from hashlib import md5, sha256
from typing import Any

from . import message as M
from .crypto import decrypt_ecb, encrypt_ecb, encrypt_ecb_block, encrypt_gcm, normalise_key
from .exceptions import (
    TuyaConnectionError,
    TuyaDecodeError,
    TuyaKeyError,
    TuyaResponseError,
)
from .version import ProtocolVersion

_LOGGER = logging.getLogger(__name__)

TuyaDeviceListener = Callable[[dict[str, Any]], None | Awaitable[None]]

DEFAULT_TIMEOUT = 6.0
_RESPONSE_CMDS = {
    M.CONTROL: {M.CONTROL, M.CONTROL_NEW, M.STATUS},
    M.CONTROL_NEW: {M.CONTROL, M.CONTROL_NEW, M.STATUS},
    M.DP_QUERY: {M.DP_QUERY, M.DP_QUERY_NEW, M.STATUS},
    M.DP_QUERY_NEW: {M.DP_QUERY, M.DP_QUERY_NEW, M.STATUS},
    M.HEART_BEAT: {M.HEART_BEAT},
    M.UPDATE_DPS: {M.UPDATE_DPS, M.STATUS},
}


class _Pending:
    __slots__ = ("cmd", "accept", "future")

    def __init__(self, cmd: int) -> None:
        self.cmd = cmd
        self.accept = _RESPONSE_CMDS.get(cmd, {cmd})
        self.future: asyncio.Future[dict[str, Any] | None] = (
            asyncio.get_running_loop().create_future()
        )


class TuyaDevice:
    """Talks the Tuya LAN protocol (3.1 - 3.5) to one device over a persistent socket."""

    def __init__(
        self,
        device_id: str,
        address: str,
        local_key: str,
        version: str | float | ProtocolVersion = "3.3",
        *,
        port: int = 6668,
        gateway_id: str | None = None,
        node_id: str | None = None,
        listener: TuyaDeviceListener | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.device_id = device_id
        self.address = address
        self.port = port
        self.version = ProtocolVersion.parse(version)
        self.gateway_id = gateway_id
        self.node_id = node_id
        self.timeout = timeout
        self._listener = listener

        try:
            self._real_key = normalise_key(local_key)
        except ValueError as err:
            raise TuyaKeyError(str(err)) from err

        self._active_key = self._real_key
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._read_task: asyncio.Task[None] | None = None
        self._seqno = 1
        self._buffer = b""
        self._pending: deque[_Pending] = deque()
        self._send_lock = asyncio.Lock()
        self._conn_lock = asyncio.Lock()
        self._raw_waiter: tuple[int, asyncio.Future[M.TuyaMessage]] | None = None
        self._closing = False

    # -- lifecycle ---------------------------------------------------------------
    @property
    def connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    def set_listener(self, listener: TuyaDeviceListener | None) -> None:
        self._listener = listener

    async def connect(self) -> None:
        async with self._conn_lock:
            if self.connected:
                return
            self._closing = False
            self._active_key = self._real_key
            self._buffer = b""
            self._seqno = 1
            try:
                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_connection(self.address, self.port), timeout=self.timeout
                )
            except (OSError, asyncio.TimeoutError) as err:
                raise TuyaConnectionError(
                    f"cannot reach {self.address}:{self.port}: {err}"
                ) from err

            self._read_task = asyncio.ensure_future(self._read_loop())

            if self.version.needs_session:
                try:
                    await self._negotiate_session()
                except BaseException:
                    await self.close()
                    raise

    async def close(self) -> None:
        self._closing = True
        if self._read_task:
            self._read_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._read_task
            self._read_task = None
        if self._writer is not None:
            self._writer.close()
            with contextlib.suppress(Exception):
                await self._writer.wait_closed()
        self._reader = self._writer = None
        while self._pending:
            pending = self._pending.popleft()
            if not pending.future.done():
                pending.future.set_exception(TuyaConnectionError("connection closed"))

    # -- public operations -----------------------------------------------------
    async def status(self) -> dict[str, Any]:
        """Query and return the full ``{dp: value}`` map."""
        result = await self._request(M.DP_QUERY)
        return _extract_dps(result)

    async def refresh_dps(self, dp_ids: list[int] | None = None) -> None:
        """Ask the device to re-report the listed DPs (3.3+); no reply expected."""
        if self.version.number < 3.3:
            return
        await self._request(
            M.UPDATE_DPS, dp_ids=dp_ids or [4, 5, 6, 18, 19, 20], expect_response=False
        )

    async def set_dp(self, dp: str | int, value: Any) -> dict[str, Any]:
        return await self.set_dps({str(dp): value})

    async def set_dps(self, dps: dict[str, Any]) -> dict[str, Any]:
        result = await self._request(M.CONTROL, dps=dps)
        return _extract_dps(result)

    async def heartbeat(self) -> None:
        await self._request(M.HEART_BEAT, expect_response=True)

    # -- request / response --------------------------------------------------
    async def _request(
        self,
        cmd: int,
        *,
        dps: dict[str, Any] | None = None,
        dp_ids: list[int] | None = None,
        expect_response: bool = True,
    ) -> dict[str, Any] | None:
        if not self.connected:
            await self.connect()

        real_cmd, payload = self._build_command(cmd, dps=dps, dp_ids=dp_ids)
        frame = self._encode(real_cmd, payload)

        async with self._send_lock:
            pending = _Pending(cmd) if expect_response else None
            if pending is not None:
                self._pending.append(pending)
            assert self._writer is not None
            try:
                self._writer.write(frame)
                await self._writer.drain()
            except OSError as err:
                if pending is not None and pending in self._pending:
                    self._pending.remove(pending)
                raise TuyaConnectionError(f"send failed: {err}") from err

        if pending is None:
            return None
        try:
            return await asyncio.wait_for(pending.future, timeout=self.timeout)
        except asyncio.TimeoutError as err:
            with contextlib.suppress(ValueError):
                self._pending.remove(pending)
            raise TuyaConnectionError(f"no response to command {cmd:#x}") from err

    def _next_seqno(self) -> int:
        seq = self._seqno
        self._seqno = (self._seqno + 1) & 0xFFFFFFFF or 1
        return seq

    # -- command payloads ---------------------------------------------------
    def _build_command(
        self, cmd: int, *, dps: dict[str, Any] | None, dp_ids: list[int] | None
    ) -> tuple[int, bytes]:
        now = int(time.time())
        dev = self.device_id
        gw = self.gateway_id or self.device_id

        if self.version.needs_session:
            if cmd in (M.CONTROL, M.CONTROL_NEW):
                data: dict[str, Any] = {"dps": dps or {}}
                if self.node_id:
                    data["cid"] = self.node_id
                    data["ctype"] = 0
                body = {"protocol": 5, "t": now, "data": data}
                return M.CONTROL_NEW, _dump(body)
            if cmd in (M.DP_QUERY, M.DP_QUERY_NEW):
                body = {"cid": self.node_id} if self.node_id else {}
                return M.DP_QUERY_NEW, _dump(body)
            if cmd == M.UPDATE_DPS:
                return M.UPDATE_DPS, _dump({"dpId": dp_ids or []})
            if cmd == M.HEART_BEAT:
                return M.HEART_BEAT, _dump({"gwId": gw, "devId": dev})
            return cmd, _dump({})

        # 3.1 - 3.3
        if cmd == M.CONTROL:
            body = {"devId": dev, "uid": dev, "t": str(now), "dps": dps or {}}
            return M.CONTROL, _dump(body)
        if cmd == M.DP_QUERY:
            body = {"gwId": gw, "devId": dev, "uid": dev, "t": str(now)}
            return M.DP_QUERY, _dump(body)
        if cmd == M.UPDATE_DPS:
            return M.UPDATE_DPS, _dump({"dpId": dp_ids or []})
        if cmd == M.HEART_BEAT:
            return M.HEART_BEAT, _dump({"gwId": gw, "devId": dev})
        return cmd, _dump({"gwId": gw, "devId": dev, "uid": dev, "t": str(now)})

    # -- framing ----------------------------------------------------------
    def _encode(self, cmd: int, payload: bytes) -> bytes:
        seqno = self._next_seqno()
        v = self.version

        if v.uses_gcm:  # 3.5
            if cmd not in M.NO_HEADER_CMDS:
                payload = v.header + payload
            key = self._active_key
            if cmd in (M.SESS_KEY_NEG_START, M.SESS_KEY_NEG_FINISH):
                key = self._real_key
            return M.pack(seqno, cmd, payload, key=key, use_gcm=True, nonce=os.urandom(12))

        if v.uses_hmac:  # 3.4
            key = self._active_key
            if cmd in (M.SESS_KEY_NEG_START, M.SESS_KEY_NEG_FINISH):
                key = self._real_key
            if cmd not in M.NO_HEADER_CMDS:
                payload = v.header + payload
            enc = encrypt_ecb(key, payload)
            return M.pack(seqno, cmd, enc, key=key, use_hmac=True)

        if v.number >= 3.2:  # 3.2 / 3.3
            enc = encrypt_ecb(self._real_key, payload)
            if cmd not in M.NO_HEADER_CMDS:
                enc = v.header + enc
            return M.pack(seqno, cmd, enc, key=self._real_key)

        # 3.1
        if cmd == M.CONTROL:
            import base64

            enc = base64.b64encode(encrypt_ecb(self._real_key, payload))
            signature = md5(
                b"data=" + enc + b"||lpv=3.1||" + self._real_key
            ).hexdigest()[8:24]
            enc = b"3.1" + signature.encode("latin1") + enc
            return M.pack(seqno, cmd, enc, key=self._real_key)
        return M.pack(seqno, cmd, payload, key=self._real_key)

    # -- session key negotiation (3.4 / 3.5) --------------------------------
    async def _negotiate_session(self) -> None:
        local_nonce = os.urandom(16)

        resp = await self._exchange_raw(M.SESS_KEY_NEG_START, local_nonce, M.SESS_KEY_NEG_RESP)
        payload = resp.payload
        if self.version.number == 3.4:
            payload = decrypt_ecb(self._real_key, payload)
        elif len(payload) >= 52:
            # 6699 frames keep the 4-byte retcode inside the plaintext.
            payload = payload[4:]
        if len(payload) < 48:
            raise TuyaKeyError("session negotiation: response too short (wrong key/version?)")

        remote_nonce = payload[:16]
        want = _hmac.new(self._real_key, local_nonce, sha256).digest()
        if not _hmac.compare_digest(want, payload[16:48]):
            raise TuyaKeyError("session negotiation: HMAC mismatch (local key is wrong)")

        finish = _hmac.new(self._real_key, remote_nonce, sha256).digest()
        await self._exchange_raw(M.SESS_KEY_NEG_FINISH, finish, None)

        xored = bytes(a ^ b for a, b in zip(local_nonce, remote_nonce, strict=True))
        if self.version.number == 3.4:
            self._active_key = encrypt_ecb_block(self._real_key, xored)
        else:  # 3.5
            ciphertext, _tag = encrypt_gcm(self._real_key, local_nonce[:12], xored, b"")
            self._active_key = ciphertext
        _LOGGER.debug("%s: session key negotiated (v%s)", self.device_id, self.version)

    async def _exchange_raw(
        self, cmd: int, payload: bytes, expect_cmd: int | None
    ) -> M.TuyaMessage:
        """Send a negotiation frame and (optionally) wait for a specific cmd reply."""
        fut: asyncio.Future[M.TuyaMessage] = asyncio.get_running_loop().create_future()
        self._raw_waiter = (expect_cmd, fut) if expect_cmd is not None else None
        frame = self._encode(cmd, payload)
        assert self._writer is not None
        self._writer.write(frame)
        await self._writer.drain()
        if expect_cmd is None:
            return M.TuyaMessage(0, cmd, 0, b"")
        try:
            return await asyncio.wait_for(fut, timeout=self.timeout)
        except asyncio.TimeoutError as err:
            raise TuyaKeyError("session negotiation timed out") from err
        finally:
            self._raw_waiter = None

    # -- read loop -------------------------------------------------------
    async def _read_loop(self) -> None:
        assert self._reader is not None
        try:
            while not self._closing:
                chunk = await self._reader.read(4096)
                if not chunk:
                    break
                self._buffer += chunk
                self._buffer = self._consume(self._buffer)
        except asyncio.CancelledError:
            raise
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("%s: read loop error: %s", self.device_id, err)
        finally:
            if not self._closing:
                self._fail_pending(TuyaConnectionError("connection lost"))

    def _consume(self, buffer: bytes) -> bytes:
        # During 3.4 negotiation the reply is HMAC'd with the real key; afterwards
        # with the session key. _active_key tracks whichever is current.
        messages, leftover = M.unpack_stream(
            buffer, key=self._active_key, use_hmac=self.version.uses_hmac
        )
        for msg in messages:
            self._handle_message(msg)
        return leftover

    def _handle_message(self, msg: M.TuyaMessage) -> None:
        # Raw negotiation path first.
        waiter = self._raw_waiter
        if waiter is not None and msg.cmd == waiter[0] and not waiter[1].done():
            waiter[1].set_result(msg)
            return

        if not msg.checksum_ok:
            _LOGGER.debug("%s: dropping frame with bad checksum (cmd %#x)", self.device_id, msg.cmd)
            return

        try:
            decoded = self._decode_payload(msg.payload)
        except TuyaDecodeError as err:
            _LOGGER.debug("%s: undecodable payload: %s", self.device_id, err)
            return

        if msg.retcode and not decoded:
            self._resolve(msg, exception=TuyaResponseError(f"device error {msg.retcode}", msg.retcode))
            return

        dps = _extract_dps(decoded) if decoded else {}

        # Match this frame to the oldest pending request that accepts its cmd.
        # (v3.5 devices reply with their own global seqno, so cmd-FIFO is the
        # only portable correlation.)
        resolved = self._resolve(msg, result=decoded)

        # STATUS pushes (and any DP data not consumed by a request) go to the listener.
        if dps and (msg.cmd == M.STATUS or not resolved):
            self._dispatch(dps)

    def _resolve(
        self,
        msg: M.TuyaMessage,
        *,
        result: dict[str, Any] | None = None,
        exception: Exception | None = None,
    ) -> bool:
        target: _Pending | None = None
        for pending in self._pending:
            if pending.future.done():
                continue
            if msg.cmd in pending.accept:
                target = pending
                break
        if target is None:
            return False
        self._pending.remove(target)
        if exception is not None:
            target.future.set_exception(exception)
        else:
            target.future.set_result(result)
        return True

    def _fail_pending(self, err: Exception) -> None:
        while self._pending:
            pending = self._pending.popleft()
            if not pending.future.done():
                pending.future.set_exception(err)

    def _dispatch(self, dps: dict[str, Any]) -> None:
        if self._listener is None:
            return
        res = self._listener({"dps": dps})
        if asyncio.iscoroutine(res):
            asyncio.ensure_future(res)

    # -- payload decoding ---------------------------------------------------
    def _decode_payload(self, payload: bytes) -> dict[str, Any] | None:
        if not payload:
            return None
        v = self.version

        if v == ProtocolVersion.V31 or payload.startswith(b"3.1"):
            if payload.startswith(b"3.1"):
                body = payload[3 + 16 :]
                payload = decrypt_ecb(self._real_key, base64.b64decode(body))
            # else plaintext JSON
        elif v.uses_gcm:  # 3.5 - already decrypted by the framer
            if payload.startswith(b"3.5"):
                payload = payload[15:]
        elif v.uses_hmac:  # 3.4 - whole body is ECB(session_key)
            payload = decrypt_ecb(self._active_key, payload)
            if payload.startswith(b"3.4"):
                payload = payload[15:]
        elif v.number >= 3.2:  # 3.2 / 3.3
            if payload.startswith(v.value.encode("latin1")):
                payload = payload[15:]
            if not payload.startswith(b"{"):
                payload = decrypt_ecb(self._real_key, payload)

        payload = payload.strip(b"\x00").strip()
        if not payload:
            return None
        if not payload.startswith(b"{"):
            raise TuyaDecodeError(f"not JSON: {payload[:32]!r}")
        try:
            obj = json.loads(payload)
        except ValueError as err:
            raise TuyaDecodeError(str(err)) from err
        if isinstance(obj, dict) and "dps" not in obj:
            data = obj.get("data")
            if isinstance(data, dict) and "dps" in data:
                obj["dps"] = data["dps"]
        return obj


def _dump(obj: dict[str, Any]) -> bytes:
    return json.dumps(obj, separators=(",", ":")).encode("utf-8")


def _extract_dps(obj: dict[str, Any] | None) -> dict[str, Any]:
    if not obj:
        return {}
    dps = obj.get("dps")
    if isinstance(dps, dict):
        return {str(k): v for k, v in dps.items()}
    return {}
