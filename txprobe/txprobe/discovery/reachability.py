"""Active reachability test — TCP connect + Bitcoin P2P version handshake."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import random
import struct
import sys
import time
from dataclasses import dataclass

from ..config import ReachabilityConfig

log = logging.getLogger(__name__)

# Testnet4 P2P constants (from chainparams.cpp:359-363)
TESTNET4_MAGIC: bytes = b'\x1c\x16\x3f\x28'
PROTOCOL_VERSION: int = 70016
USER_AGENT: str = "/TxProbe:0.1/"
P2P_HEADER_SIZE: int = 24  # 4 magic + 12 command + 4 length + 4 checksum


async def test_reachability(
    host: str,
    port: int,
    network: str,
    config: ReachabilityConfig,
) -> bool:
    """Test if a single node is reachable and speaks Bitcoin P2P.

    Steps:
        1. TCP connect (direct for clearnet, SOCKS5 for .onion via Tor proxy).
        2. Send a Bitcoin P2P ``version`` message.
        3. Read response header (24 bytes).
        4. Verify magic == TESTNET4_MAGIC and command == "version".
        5. Close connection.

    No ``verack`` exchange is needed — receiving a ``version`` reply is
    sufficient proof that the remote speaks Bitcoin P2P on testnet4.

    Returns:
        True if all steps succeed within the timeout.
    """
    timeout = (
        config.tor_timeout_sec if network == "onion"
        else config.clearnet_timeout_sec
    )
    try:
        reader, writer = await asyncio.wait_for(
            _open_connection(host, port, network, config),
            timeout=timeout,
        )
    except (asyncio.TimeoutError, OSError, Exception) as e:
        log.debug("Connect failed %s:%d (%s): %s", host, port, network, e)
        return False

    try:
        # Send version message
        version_msg = _build_version_message(host, port)
        writer.write(version_msg)
        await writer.drain()

        # Read response header
        header = await asyncio.wait_for(
            reader.readexactly(P2P_HEADER_SIZE),
            timeout=timeout,
        )
        magic, command, payload_len, _checksum = _parse_message_header(header)

        if magic != TESTNET4_MAGIC:
            log.debug("Wrong magic from %s:%d: %s", host, port, magic.hex())
            return False

        if command != "version":
            log.debug("Expected 'version' from %s:%d, got '%s'", host, port, command)
            return False

        # Drain the version payload so we don't leave data in the buffer
        if payload_len > 0:
            await asyncio.wait_for(
                reader.readexactly(payload_len),
                timeout=timeout,
            )

        return True

    except (asyncio.TimeoutError, asyncio.IncompleteReadError, OSError, Exception) as e:
        log.debug("Handshake failed %s:%d: %s", host, port, e)
        return False
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except OSError:
            pass


async def batch_test_reachability(
    candidates: list[tuple[str, int, str]],
    config: ReachabilityConfig,
    show_progress: bool = True,
) -> list[bool]:
    """Test reachability of many candidates with concurrency limits and live progress bar.

    Separates clearnet and Tor/IPv6 candidates and tests them with different
    concurrency limits via ``asyncio.Semaphore``.

    Args:
        candidates: List of ``(host, port, network)`` tuples.
        config: Reachability configuration (timeouts, concurrency).
        show_progress: Whether to display a tqdm progress bar (if stdout is a TTY).

    Returns:
        List of booleans, same length and order as *candidates*.
    """
    if not candidates:
        return []

    clearnet_sem = asyncio.Semaphore(config.clearnet_concurrency)
    tor_sem = asyncio.Semaphore(config.tor_concurrency)

    passed_count = 0
    completed_count = 0
    total = len(candidates)
    lock = asyncio.Lock()

    pbar = None
    if show_progress and sys.stdout.isatty():
        from tqdm import tqdm
        pbar = tqdm(
            total=total,
            desc="Reachability",
            unit="addr",
            ncols=80,
            mininterval=0.4,
            file=sys.stdout,
            leave=True,
        )

    async def _test_one(host: str, port: int, network: str) -> bool:
        nonlocal passed_count, completed_count
        sem = tor_sem if (network in ("onion", "ipv6") or ":" in host) else clearnet_sem
        async with sem:
            ok = await test_reachability(host, port, network, config)

        async with lock:
            completed_count += 1
            if ok:
                passed_count += 1
            if pbar is not None:
                rate = (passed_count / completed_count * 100) if completed_count > 0 else 0.0
                pbar.set_postfix({"pass": passed_count, "rate": f"{rate:.1f}%"}, refresh=False)
                pbar.update(1)
            elif show_progress and (completed_count % 250 == 0 or completed_count == total):
                rate = (passed_count / completed_count * 100) if completed_count > 0 else 0.0
                log.info(
                    "Reachability progress: %d/%d (%.1f%%) | passed: %d (%.1f%%)",
                    completed_count,
                    total,
                    completed_count / total * 100,
                    passed_count,
                    rate,
                )
        return ok

    try:
        tasks = [
            _test_one(host, port, network)
            for host, port, network in candidates
        ]
        return list(await asyncio.gather(*tasks))
    finally:
        if pbar is not None:
            pbar.close()


# ── P2P message construction ──


def _build_version_message(dest_host: str, dest_port: int) -> bytes:
    """Build a complete Bitcoin P2P version message (header + payload).

    The version message is the first message in the Bitcoin P2P handshake.
    We construct a minimal but valid one.
    """
    payload = _build_version_payload(dest_host, dest_port)
    return _wrap_p2p_message(b"version", payload)


def _build_version_payload(dest_host: str, dest_port: int) -> bytes:
    """Build the version message payload.

    Wire layout:
        int32   nVersion
        uint64  nServices
        int64   nTime
        net_addr addrTo    (26 bytes, no timestamp)
        net_addr addrFrom  (26 bytes, no timestamp)
        uint64  nNonce
        var_str strSubVer
        int32   nStartingHeight
        bool    fRelay
    """
    r = b""
    r += struct.pack("<i", PROTOCOL_VERSION)      # nVersion
    r += struct.pack("<Q", 0)                      # nServices (we offer nothing)
    r += struct.pack("<q", int(time.time()))        # nTime
    r += _serialize_net_addr(0, dest_host, dest_port)  # addrTo
    r += _serialize_net_addr(0, "0.0.0.0", 0)         # addrFrom
    r += struct.pack("<Q", random.getrandbits(64))     # nNonce
    # strSubVer (varint length + utf-8 bytes)
    sub_ver = USER_AGENT.encode("utf-8")
    r += _ser_compact_size(len(sub_ver)) + sub_ver
    r += struct.pack("<i", 0)                      # nStartingHeight
    r += struct.pack("<B", 0)                      # fRelay = false
    return r


def _serialize_net_addr(services: int, ip: str, port: int) -> bytes:
    """Serialize a CAddress in addrv1 format WITHOUT timestamp (for version msg).

    Layout: 8 bytes services + 16 bytes IPv4-mapped-IPv6 (or native IPv6) + 2 bytes port (big-endian).
    """
    import socket as _socket
    r = struct.pack("<Q", services)
    try:
        ipv4_bytes = _socket.inet_aton(ip)
        # IPv4-mapped IPv6: 10 bytes 0x00 + 2 bytes 0xff + 4 bytes IPv4
        r += b"\x00" * 10 + b"\xff\xff" + ipv4_bytes
    except OSError:
        try:
            # Native IPv6: 16 bytes
            ipv6_bytes = _socket.inet_pton(_socket.AF_INET6, ip)
            r += ipv6_bytes
        except (OSError, ValueError):
            # Not a valid IPv4 or IPv6 (e.g. .onion) — use all zeros
            r += b"\x00" * 16
    r += struct.pack(">H", port)
    return r


def _wrap_p2p_message(command: bytes, payload: bytes) -> bytes:
    """Wrap a payload into a Bitcoin P2P message with header.

    Header layout:
        4 bytes  magic
        12 bytes command (null-padded)
        4 bytes  payload length (LE uint32)
        4 bytes  checksum (first 4 bytes of double-SHA256 of payload)
    """
    cmd_padded = command.ljust(12, b"\x00")
    checksum = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    header = TESTNET4_MAGIC + cmd_padded + struct.pack("<I", len(payload)) + checksum
    return header + payload


def _parse_message_header(data: bytes) -> tuple[bytes, str, int, bytes]:
    """Parse a 24-byte P2P message header.

    Returns:
        (magic, command, payload_length, checksum)
    """
    magic = data[0:4]
    command = data[4:16].rstrip(b"\x00").decode("ascii", errors="replace")
    payload_length = struct.unpack("<I", data[16:20])[0]
    checksum = data[20:24]
    return magic, command, payload_length, checksum


def _ser_compact_size(n: int) -> bytes:
    """Serialize an integer as a Bitcoin CompactSize uint."""
    if n < 253:
        return struct.pack("<B", n)
    elif n <= 0xFFFF:
        return b"\xfd" + struct.pack("<H", n)
    elif n <= 0xFFFFFFFF:
        return b"\xfe" + struct.pack("<I", n)
    else:
        return b"\xff" + struct.pack("<Q", n)


async def _open_connection(
    host: str,
    port: int,
    network: str,
    config: ReachabilityConfig,
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Open a TCP connection — direct for clearnet IPv4, SOCKS5 for Tor and IPv6.

    For .onion and IPv6 addresses, routes through the Tor SOCKS5 proxy to
    bypass host IPv6 connectivity limitations.
    """
    if network in ("onion", "ipv6") or ":" in host:
        return await _open_tor_connection(host, port, config)
    try:
        return await asyncio.open_connection(host, port)
    except OSError as e:
        if "unreachable" in str(e).lower():
            return await _open_tor_connection(host, port, config)
        raise


async def _open_tor_connection(
    host: str,
    port: int,
    config: ReachabilityConfig,
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Open a TCP connection through the Tor SOCKS5 proxy.

    Uses the ``python_socks`` library for async SOCKS5 support.
    """
    from python_socks.async_.asyncio.v2 import Proxy

    proxy = Proxy.from_url(
        f"socks5://{config.tor_proxy_host}:{config.tor_proxy_port}"
    )
    sock = await proxy.connect(dest_host=host, dest_port=port)
    # Wrap the raw socket into asyncio streams
    reader, writer = await asyncio.open_connection(sock=sock)
    return reader, writer
