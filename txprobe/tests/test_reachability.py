"""Tests for address normalization, reachability, and P2P message construction."""

import struct

import pytest

from txprobe.models.node import NodeIdentity, _has_port, _is_ipv6, normalize_addr, split_addr_port
from txprobe.discovery.reachability import (
    TESTNET4_MAGIC,
    _build_version_message,
    _parse_message_header,
    _serialize_net_addr,
    _wrap_p2p_message,
    batch_test_reachability,
)


# ── _has_port tests ──


class TestHasPort:
    def test_ipv4_with_port(self):
        assert _has_port("1.2.3.4:48333") is True

    def test_ipv6_bracketed_with_port(self):
        assert _has_port("[::1]:48333") is True

    def test_onion_with_port(self):
        assert _has_port("abc.onion:48333") is True

    def test_ipv4_no_port(self):
        assert _has_port("1.2.3.4") is False

    def test_ipv6_bare(self):
        assert _has_port("::1") is False

    def test_ipv6_bracketed_no_port(self):
        assert _has_port("[::1]") is False

    def test_onion_no_port(self):
        assert _has_port("abc.onion") is False

    def test_invalid_port_text(self):
        assert _has_port("[::1]:abc") is False

    def test_port_zero(self):
        assert _has_port("1.2.3.4:0") is False

    def test_port_too_high(self):
        assert _has_port("1.2.3.4:99999") is False

    def test_port_65535(self):
        assert _has_port("1.2.3.4:65535") is True


# ── normalize_addr tests ──


class TestNormalizeAddr:
    def test_ipv4(self):
        assert normalize_addr("1.2.3.4", 48333) == "1.2.3.4:48333"

    def test_ipv6_brackets(self):
        assert normalize_addr("::ffff:1.2.3.4", 48333, "ipv6") == "[::ffff:1.2.3.4]:48333"

    def test_ipv6_auto_detect(self):
        assert normalize_addr("2001:db8::1", 48333) == "[2001:db8::1]:48333"

    def test_onion(self):
        assert normalize_addr("abc.onion", 48333) == "abc.onion:48333"

    def test_already_has_port_passthrough(self):
        assert normalize_addr("1.2.3.4:48333", 0) == "1.2.3.4:48333"

    def test_ipv6_already_formatted(self):
        assert normalize_addr("[::1]:48333", 0) == "[::1]:48333"


# ── split_addr_port tests ──


class TestSplitAddrPort:
    def test_ipv4(self):
        assert split_addr_port("1.2.3.4:48333") == ("1.2.3.4", 48333)

    def test_ipv6(self):
        assert split_addr_port("[::1]:48333") == ("::1", 48333)

    def test_onion(self):
        host, port = split_addr_port("abc.onion:48333")
        assert host == "abc.onion"
        assert port == 48333

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            split_addr_port("noporthere")


# ── P2P message tests ──


class TestP2PMessages:
    def test_version_message_header(self):
        msg = _build_version_message("1.2.3.4", 48333)
        # First 4 bytes should be testnet4 magic
        assert msg[:4] == TESTNET4_MAGIC
        # Bytes 4-16: command "version" null-padded to 12 bytes
        command = msg[4:16].rstrip(b"\x00")
        assert command == b"version"

    def test_version_message_has_payload(self):
        msg = _build_version_message("1.2.3.4", 48333)
        payload_len = struct.unpack("<I", msg[16:20])[0]
        assert payload_len > 0
        # Total message should be header (24) + payload
        assert len(msg) == 24 + payload_len

    def test_parse_header_roundtrip(self):
        payload = b"test payload"
        msg = _wrap_p2p_message(b"ping", payload)
        magic, command, length, checksum = _parse_message_header(msg[:24])
        assert magic == TESTNET4_MAGIC
        assert command == "ping"
        assert length == len(payload)

    def test_verack_empty_payload(self):
        msg = _wrap_p2p_message(b"verack", b"")
        _, command, length, _ = _parse_message_header(msg[:24])
        assert command == "verack"
        assert length == 0
        assert len(msg) == 24  # header only


class TestSerializationAndBatchReachability:
    def test_serialize_net_addr_ipv4(self):
        import socket
        raw = _serialize_net_addr(1, "1.2.3.4", 48333)
        assert len(raw) == 26
        services, mapped, port = struct.unpack("<Q16sH", raw)
        assert services == 1
        assert mapped == b"\x00" * 10 + b"\xff\xff" + socket.inet_aton("1.2.3.4")
        assert struct.unpack(">H", raw[24:26])[0] == 48333

    def test_serialize_net_addr_ipv6(self):
        import socket
        raw = _serialize_net_addr(0, "2001:db8::1", 48333)
        assert len(raw) == 26
        services = struct.unpack("<Q", raw[:8])[0]
        assert services == 0
        ipv6_bytes = raw[8:24]
        assert ipv6_bytes == socket.inet_pton(socket.AF_INET6, "2001:db8::1")
        port = struct.unpack(">H", raw[24:26])[0]
        assert port == 48333

    def test_serialize_net_addr_onion_fallback(self):
        raw = _serialize_net_addr(0, "abcdef.onion", 48333)
        assert len(raw) == 26
        assert raw[8:24] == b"\x00" * 16

    @pytest.mark.asyncio
    async def test_batch_reachability_empty(self):
        from txprobe.config import ReachabilityConfig
        res = await batch_test_reachability([], ReachabilityConfig())
        assert res == []

    @pytest.mark.asyncio
    async def test_batch_reachability_progress(self, monkeypatch):
        from unittest.mock import AsyncMock, patch
        from txprobe.config import ReachabilityConfig

        candidates = [
            ("1.1.1.1", 48333, "ipv4"),
            ("2.2.2.2", 48333, "ipv4"),
            ("2001:db8::1", 48333, "ipv6"),
            ("foo.onion", 48333, "onion"),
        ]

        async def mock_test(h, p, net, cfg):
            return net != "onion"

        with patch("txprobe.discovery.reachability.test_reachability", side_effect=mock_test):
            res = await batch_test_reachability(candidates, ReachabilityConfig(), show_progress=False)
            assert res == [True, True, True, False]

            # Also test with show_progress=True (TTY mock or fallback)
            res2 = await batch_test_reachability(candidates, ReachabilityConfig(), show_progress=True)
            assert res2 == [True, True, True, False]

