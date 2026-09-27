"""Active reachability test — TCP connect + Bitcoin P2P version handshake."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import random
import struct
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
) -> list[bool]:
    """Test reachability of many candidates with concurrency limits.

    Separates clearnet and Tor candidates and tests them with different
    concurrency limits via ``asyncio.Semaphore``.

    Args:
        candidates: List of ``(host, port, network)`` tuples.
        config: Reachability configuration (timeouts, concurrency).

    Returns:
        List of booleans, same length and order as *candidates*.
    """
    clearnet_sem = asyncio.Semaphore(config.clearnet_concurrency)
    tor_sem = asyncio.Semaphore(config.tor_concurrency)

    async def _test_one(host: str, port: int, network: str) -> bool:
        sem = tor_sem if network == "onion" else clearnet_sem
        async with sem:
            return await test_reachability(host, port, network, config)

    tasks = [
        _test_one(host, port, network)
        for host, port, network in candidates
    ]
    return list(await asyncio.gather(*tasks))


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

    Layout: 8 bytes services + 16 bytes IPv4-mapped-IPv6 + 2 bytes port (big-endian).
    """
    r = struct.pack("<Q", services)
    # IPv4-mapped IPv6: 10 bytes 0x00 + 2 bytes 0xff + 4 bytes IPv4
    try:
        import socket as _socket
        ipv4_bytes = _socket.inet_aton(ip)
        r += b"\x00" * 10 + b"\xff\xff" + ipv4_bytes
    except OSError:
        # Not a valid IPv4 — use all zeros
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
    """Open a TCP connection — direct for clearnet, SOCKS5 for Tor.

    For .onion addresses, routes through the Tor SOCKS5 proxy.
    """
    if network == "onion":
        return await _open_tor_connection(host, port, config)
    return await asyncio.open_connection(host, port)


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
