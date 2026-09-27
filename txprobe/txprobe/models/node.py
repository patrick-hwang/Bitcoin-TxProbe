"""Node identity and candidate data models."""

from dataclasses import dataclass
from enum import IntEnum


class CandidatePriority(IntEnum):
    """Priority of a candidate address. Lower = higher priority."""
    GROUNDTRUTH_PEER = 0   # Peer of groundtruth nodes (1-5) via getpeerinfo
    PROBE_PEER       = 1   # Peer of probe nodes (0,6) via getpeerinfo
    DNS_SEED         = 2   # From DNS seed resolution
    ADDRMAN          = 3   # From address manager (getnodeaddresses)


@dataclass(frozen=True)
class NodeIdentity:
    """Identity of a node — normalized as 'address:port'.

    Format:
        IPv4:  "1.2.3.4:48333"
        IPv6:  "[::ffff:1.2.3.4]:48333"
        Onion: "abc...xyz.onion:48333"
    """
    addr: str


@dataclass(frozen=True)
class CandidateNode:
    """A discovered candidate node with its priority and source."""
    identity: NodeIdentity
    priority: CandidatePriority
    network: str              # "ipv4", "ipv6", "onion", "i2p", "cjdns"
    source_node_id: int       # Which of our nodes (0-6) discovered this, or -1 for DNS
    last_seen: int            # Unix timestamp (from getnodeaddresses "time" field, or 0)


def normalize_addr(address: str, port: int, network: str = "") -> str:
    """Normalize an address to 'host:port' format.

    Handles the format difference between getpeerinfo (combined "host:port")
    and getnodeaddresses (separate "address" + "port" fields).

    IPv6 addresses are always wrapped in brackets: [addr]:port

    Args:
        address: Raw address string (may or may not include port).
        port: Port number (used only if address doesn't already contain port).
        network: Optional network hint ("ipv4", "ipv6", "onion", etc.).

    Returns:
        Normalized "host:port" string.
    """
    if _has_port(address):
        return address

    # Separate address + port — combine with IPv6 bracket handling
    if network == "ipv6" or _is_ipv6(address):
        return f"[{address}]:{port}"
    return f"{address}:{port}"


def _has_port(addr: str) -> bool:
    """Check if an address string already contains a valid numeric port suffix.

    Examples:
        "1.2.3.4:48333"       → True
        "[::1]:48333"         → True
        "abc.onion:48333"     → True
        "1.2.3.4"             → False
        "::1"                 → False
        "[::1]"               → False
        "abc.onion"           → False
        "[::1]:abc"           → False
    """
    if addr.startswith('['):
        if ']:' not in addr:
            return False
        _, port_str = addr.rsplit(']:', 1)
        return port_str.isdigit() and 1 <= int(port_str) <= 65535

    if ':' not in addr:
        return False

    host, port_str = addr.rsplit(':', 1)
    if ':' in host:
        # Multiple colons in host part → IPv6 address, not a port separator
        return False

    return port_str.isdigit() and 1 <= int(port_str) <= 65535


def _is_ipv6(address: str) -> bool:
    """Check if a raw address (without port) looks like IPv6."""
    return ':' in address and not address.endswith('.onion')


def split_addr_port(addr: str) -> tuple[str, int]:
    """Split a normalized 'host:port' string into (host, port).

    For IPv6, strips the brackets: "[::1]:48333" → ("::1", 48333).
    For IPv4/onion: "1.2.3.4:48333" → ("1.2.3.4", 48333).

    Raises:
        ValueError: If the address does not contain a valid port.
    """
    if addr.startswith('['):
        if ']:' not in addr:
            raise ValueError(f"Invalid bracketed address: {addr!r}")
        bracket_end = addr.index(']')
        host = addr[1:bracket_end]
        port = int(addr[bracket_end + 2:])
        return host, port

    last_colon = addr.rfind(':')
    if last_colon == -1:
        raise ValueError(f"No port in address: {addr!r}")
    host = addr[:last_colon]
    port = int(addr[last_colon + 1:])
    return host, port
