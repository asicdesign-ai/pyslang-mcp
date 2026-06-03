from __future__ import annotations

import asyncio

import pytest
from starlette.testclient import TestClient

from pyslang_mcp.auth import StaticBearerTokenVerifier
from pyslang_mcp.server import create_server

pytestmark = pytest.mark.security


def test_static_bearer_token_verifier_accepts_expected_token() -> None:
    verifier = StaticBearerTokenVerifier("secret-token")

    access = asyncio.run(verifier.verify_token("secret-token"))

    assert access is not None
    assert access.client_id == "pyslang-mcp-internal"
    assert access.scopes == ["pyslang-mcp"]


def test_static_bearer_token_verifier_rejects_wrong_token() -> None:
    verifier = StaticBearerTokenVerifier("secret-token")

    assert asyncio.run(verifier.verify_token("wrong-token")) is None


def test_static_bearer_token_verifier_rejects_empty_configured_token() -> None:
    with pytest.raises(ValueError):
        StaticBearerTokenVerifier(" ")


def test_http_auth_blocks_mcp_requests_without_expected_bearer_token() -> None:
    app = create_server(host="0.0.0.0", http_bearer_token="secret-token").streamable_http_app()

    with TestClient(app) as client:
        health = client.get("/healthz")
        missing = client.get("/mcp")
        wrong = client.get("/mcp", headers={"Authorization": "Bearer wrong-token"})
        accepted = client.get("/mcp", headers={"Authorization": "Bearer secret-token"})

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert accepted.status_code != 401
