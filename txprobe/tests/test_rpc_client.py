"""Tests for the async Bitcoin RPC client."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from txprobe.rpc.client import AsyncBitcoinRpc, RpcError


@pytest.fixture
def rpc():
    """Create an AsyncBitcoinRpc without opening a session."""
    return AsyncBitcoinRpc("127.0.0.1", 48347, "user", "pass")


def test_url_basic(rpc):
    assert rpc._url == "http://127.0.0.1:48347"


def test_url_with_wallet():
    r = AsyncBitcoinRpc("127.0.0.1", 48347, "user", "pass", wallet="mywallet")
    assert r._url == "http://127.0.0.1:48347/wallet/mywallet"


def test_auth_credentials(rpc):
    assert rpc._user == "user"
    assert rpc._password == "pass"
    assert rpc._auth_header.startswith("Basic ")


@pytest.mark.asyncio
async def test_call_formats_json():
    """call() should POST correct JSON-RPC payload."""
    rpc = AsyncBitcoinRpc("127.0.0.1", 48347, "u", "p")

    mock_resp = AsyncMock()
    mock_resp.json = AsyncMock(return_value={"result": [], "error": None})
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.post = MagicMock(return_value=mock_resp)

    rpc._session = mock_session

    result = await rpc.call("getpeerinfo")

    # Verify the POST was called with correct JSON
    call_args = mock_session.post.call_args
    posted_json = call_args.kwargs.get("json") or call_args[1].get("json")
    assert posted_json["method"] == "getpeerinfo"
    assert posted_json["params"] == []
    assert posted_json["jsonrpc"] == "2.0"
    assert result == []


@pytest.mark.asyncio
async def test_call_returns_result():
    """call() should return the 'result' field."""
    rpc = AsyncBitcoinRpc("127.0.0.1", 48347, "u", "p")

    mock_resp = AsyncMock()
    mock_resp.json = AsyncMock(return_value={"result": 42, "error": None})
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.post = MagicMock(return_value=mock_resp)
    rpc._session = mock_session

    result = await rpc.call("getblockcount")
    assert result == 42


@pytest.mark.asyncio
async def test_call_raises_on_error():
    """call() should raise RpcError when response has error."""
    rpc = AsyncBitcoinRpc("127.0.0.1", 48347, "u", "p")

    mock_resp = AsyncMock()
    mock_resp.json = AsyncMock(return_value={
        "result": None,
        "error": {"code": -28, "message": "Loading block index..."},
    })
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.post = MagicMock(return_value=mock_resp)
    rpc._session = mock_session

    with pytest.raises(RpcError) as exc_info:
        await rpc.call("getblockcount")
    assert exc_info.value.code == -28


@pytest.mark.asyncio
async def test_batch_sends_array():
    """call_batch() should POST a JSON array of requests."""
    rpc = AsyncBitcoinRpc("127.0.0.1", 48347, "u", "p")

    mock_resp = AsyncMock()
    mock_resp.json = AsyncMock(return_value=[
        {"id": 1, "result": None, "error": None},
        {"id": 2, "result": None, "error": None},
    ])
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.post = MagicMock(return_value=mock_resp)
    rpc._session = mock_session

    results = await rpc.call_batch([
        ("addnode", "1.2.3.4:48333", "onetry"),
        ("addnode", "5.6.7.8:48333", "onetry"),
    ])

    call_args = mock_session.post.call_args
    posted_json = call_args.kwargs.get("json") or call_args[1].get("json")
    assert isinstance(posted_json, list)
    assert len(posted_json) == 2
    assert posted_json[0]["method"] == "addnode"
    assert posted_json[0]["params"] == ["1.2.3.4:48333", "onetry"]
    assert len(results) == 2
