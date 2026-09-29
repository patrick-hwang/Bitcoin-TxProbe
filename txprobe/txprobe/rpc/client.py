"""Async JSON-RPC client for Bitcoin Core using aiohttp."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

import aiohttp

log = logging.getLogger(__name__)


class RpcError(Exception):
    """Error returned by the Bitcoin Core JSON-RPC server."""

    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"RPC error {code}: {message}")


class AsyncBitcoinRpc:
    """Async JSON-RPC client for Bitcoin Core.

    Uses aiohttp to make HTTP POST requests directly to the Bitcoin Core
    JSON-RPC server, instead of shelling out to bitcoin-cli.

    Usage::

        async with AsyncBitcoinRpc("127.0.0.1", 48347, "user", "pass") as rpc:
            peers = await rpc.getpeerinfo()
    """

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        wallet: str = "",
    ):
        self._url = f"http://{host}:{port}"
        if wallet:
            self._url += f"/wallet/{wallet}"
        self._user = user
        self._password = password
        self._auth_header = aiohttp.encode_basic_auth(user, password)
        self._session: aiohttp.ClientSession | None = None
        self._id_counter = 0

    async def open(self) -> None:
        """Create the HTTP session. Must be called before any RPC."""
        self._session = aiohttp.ClientSession(
            headers={
                "Content-Type": "application/json",
                "Authorization": self._auth_header,
            },
            timeout=aiohttp.ClientTimeout(total=120),
        )

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session:
            await self._session.close()
            self._session = None

    async def __aenter__(self) -> AsyncBitcoinRpc:
        await self.open()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    def _next_id(self) -> int:
        self._id_counter += 1
        return self._id_counter

    async def call(self, method: str, *params: Any) -> Any:
        """Make a single JSON-RPC call.

        Args:
            method: The RPC method name (e.g. "getpeerinfo").
            *params: Positional parameters for the method.

        Returns:
            The ``result`` field from the JSON-RPC response.

        Raises:
            RpcError: If the response contains an ``error`` field.
            aiohttp.ClientError: On network/connection errors.
        """
        assert self._session is not None, "Call open() or use 'async with' first"
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
            "params": list(params),
        }
        async with self._session.post(self._url, json=payload) as resp:
            body = await resp.json(content_type=None)

        if body.get("error"):
            err = body["error"]
            raise RpcError(err.get("code", -1), err.get("message", ""))
        return body.get("result")

    async def call_batch(
        self,
        calls: list[tuple[str, ...]],
        *,
        raise_on_error: bool = True,
    ) -> list[Any]:
        """Make a batch JSON-RPC call (multiple methods in one HTTP request).

        Args:
            calls: List of tuples, each being ``(method, *params)``.
            raise_on_error: If True (default), raise RpcError on the first
                error response. If False, log a warning and append None for
                any failed call.

        Returns:
            List of ``result`` values, in the same order as *calls*.

        Raises:
            RpcError: If *raise_on_error* is True and any call returns an error.
        """
        assert self._session is not None, "Call open() or use 'async with' first"
        if not calls:
            return []

        batch = []
        for call_args in calls:
            method = call_args[0]
            params = list(call_args[1:])
            batch.append({
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": method,
                "params": params,
            })

        async with self._session.post(self._url, json=batch) as resp:
            bodies = await resp.json(content_type=None)

        # Sort by id to maintain original order
        bodies.sort(key=lambda b: b.get("id", 0))
        results: list[Any] = []
        for body in bodies:
            if body.get("error"):
                err = body["error"]
                if raise_on_error:
                    raise RpcError(err.get("code", -1), err.get("message", ""))
                log.debug(
                    "Ignoring RPC batch error %s: %s",
                    err.get("code", -1),
                    err.get("message", ""),
                )
                results.append(None)
            else:
                results.append(body.get("result"))
        return results

    # ── Convenience wrappers ──

    async def getpeerinfo(self) -> list[dict]:
        """Return data about each connected peer.

        Key fields per peer:
            id (int), addr (str "host:port"), network (str),
            connection_type (str), inbound (bool).
        """
        return await self.call("getpeerinfo")

    async def getnodeaddresses(
        self, count: int = 0, network: str = ""
    ) -> list[dict]:
        """Return known addresses from the address manager.

        Args:
            count: Max addresses to return. 0 = all.
            network: Optional filter ("ipv4", "ipv6", "onion", etc.).

        Each returned entry:
            time (int), services (int), address (str, NO port),
            port (int), network (str).
        """
        params: list[Any] = [count]
        if network:
            params.append(network)
        return await self.call("getnodeaddresses", *params)

    async def addnode(self, addr: str, command: str) -> None:
        """Add/remove/onetry a node.

        Args:
            addr: "host:port" of the target node.
            command: "add", "remove", or "onetry".
        """
        await self.call("addnode", addr, command)

    async def disconnectnode(self, addr: str) -> None:
        """Disconnect from a peer by address."""
        await self.call("disconnectnode", addr)

    async def getaddrmaninfo(self) -> dict:
        """Return address manager statistics."""
        return await self.call("getaddrmaninfo")

    async def getnetworkinfo(self) -> dict:
        """Return P2P network state and local addresses (including .onion)."""
        return await self.call("getnetworkinfo")

    async def sendinv_orphan(
        self, txs_hex: list[str], peer_ids: list[int]
    ) -> None:
        """Send inventory messages directly to specific peer IDs using custom TxProbe RPC.

        Args:
            txs_hex: List of raw transaction hex strings.
            peer_ids: List of peer numeric IDs to send INVs to.
        """
        await self.call("sendinv_orphan", txs_hex, peer_ids)

    async def clearinv_probe(self) -> dict:
        """Clear all tracked probe transactions used for INVBLOCK in memory."""
        return await self.call("clearinv_probe")

    async def createrawtransaction(
        self,
        inputs: list[dict[str, Any]],
        outputs: list[dict[str, Any]] | dict[str, Any],
    ) -> str:
        """Create a raw transaction from inputs and outputs."""
        return await self.call("createrawtransaction", inputs, outputs)

    async def decoderawtransaction(self, hexstr: str) -> dict:
        """Decode a serialized transaction hex string."""
        return await self.call("decoderawtransaction", hexstr)

