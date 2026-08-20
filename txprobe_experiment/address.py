from typing import Tuple, Optional

def endpoint_tuple_to_str(endpoint: Tuple[str, Optional[int]]) -> str:
    host, port = endpoint
    if ":" in host:
        return f"[{host}]:{port}" if port is not None else f"[{host}]"
    return f"{host}:{port}" if port is not None else host

def endpoint_str_to_tuple(address: str) -> Tuple[str, Optional[int]]:
    """Return a normalized ``(host, port)`` pair for a Bitcoin peer address."""

    address = address.strip()
    if address.startswith("["):
        closing = address.find("]")
        if closing != -1:
            host = address[1:closing]
            rest = address[closing + 1:]
            if rest.startswith(":") and rest[1:].isdigit():
                return host.lower(), int(rest[1:])
            return host.lower(), None

    host, separator, port = address.rpartition(":")
    if separator and host and port.isdigit():
        return host.lower(), int(port)
    return address.lower(), None