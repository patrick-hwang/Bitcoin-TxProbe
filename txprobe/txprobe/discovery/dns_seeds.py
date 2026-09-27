"""DNS seed resolution for Bitcoin testnet4."""

from __future__ import annotations

import asyncio
import logging
import socket

from ..models.node import CandidateNode, CandidatePriority, NodeIdentity

log = logging.getLogger(__name__)

TESTNET4_DNS_SEEDS: list[str] = [
    "seed.testnet4.bitcoin.sprovoost.nl",
    "seed.testnet4.wiz.biz",
]
TESTNET4_DEFAULT_PORT: int = 48333


async def resolve_dns_seeds(
    seeds: list[str],
    default_port: int,
    seen: set[NodeIdentity],
    candidates: list[CandidateNode],
) -> int:
    """Resolve DNS seeds and append new CandidateNodes with priority DNS_SEED.

    Uses ``asyncio.getaddrinfo`` with ``type=socket.SOCK_STREAM`` to filter
    for TCP-capable addresses only.

    Args:
        seeds: List of DNS seed hostnames to resolve.
        default_port: Default Bitcoin port (48333 for testnet4).
        seen: Set of already-seen identities (modified in-place).
        candidates: Candidate list to append to (modified in-place).

    Returns:
        Number of new candidates added.
    """
    tasks = [_resolve_one_seed(s, default_port) for s in seeds]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    added = 0
    for seed, result in zip(seeds, results):
        if isinstance(result, Exception):
            log.warning("DNS seed %s failed: %s", seed, result)
            continue
        for ip, port, network in result:
            identity = NodeIdentity(addr=f"{ip}:{port}")
            if identity not in seen:
                seen.add(identity)
                candidates.append(CandidateNode(
                    identity=identity,
                    priority=CandidatePriority.DNS_SEED,
                    network=network,
                    source_node_id=-1,
                    last_seen=0,
                ))
                added += 1
    return added


async def _resolve_one_seed(
    hostname: str,
    default_port: int,
) -> list[tuple[str, int, str]]:
    """Resolve one DNS seed hostname.

    Returns:
        List of (formatted_addr, port, network) tuples.
        IPv6 addresses are wrapped in brackets: "[::1]".
    """
    loop = asyncio.get_running_loop()
    results = await loop.getaddrinfo(
        hostname,
        None,
        family=socket.AF_UNSPEC,
        type=socket.SOCK_STREAM,
    )

    seen_ips: set[str] = set()
    resolved: list[tuple[str, int, str]] = []

    for family, _type, _proto, _canonname, sockaddr in results:
        ip = sockaddr[0]
        if ip in seen_ips:
            continue
        seen_ips.add(ip)

        if family == socket.AF_INET6:
            formatted = f"[{ip}]"
            network = "ipv6"
        else:
            formatted = ip
            network = "ipv4"

        resolved.append((formatted, default_port, network))

    return resolved
