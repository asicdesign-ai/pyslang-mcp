from __future__ import annotations

import pytest

import pyslang_mcp.__main__ as cli


def test_main_runs_default_stdio_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: dict[str, str] = {}

    class DummyServer:
        def run(self, transport: str) -> None:
            observed["transport"] = transport

    monkeypatch.setattr(cli, "create_server", lambda **_kwargs: DummyServer())

    assert cli.main([]) == 0
    assert observed["transport"] == "stdio"


def test_main_ignores_http_token_for_stdio_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: dict[str, object] = {}

    class DummyServer:
        def run(self, transport: str) -> None:
            observed["transport"] = transport

    def create_dummy_server(**kwargs: object) -> DummyServer:
        observed["kwargs"] = kwargs
        return DummyServer()

    monkeypatch.setattr(cli, "create_server", create_dummy_server)
    monkeypatch.setenv("PYSLANG_MCP_HTTP_BEARER_TOKEN", "test-token")

    assert cli.main([]) == 0
    assert observed["transport"] == "stdio"
    assert observed["kwargs"] == {}


def test_main_rejects_streamable_http_without_experimental_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DummyServer:
        def run(self, transport: str) -> None:  # pragma: no cover
            raise AssertionError(f"unexpected transport: {transport}")

    monkeypatch.setattr(cli, "create_server", lambda **_kwargs: DummyServer())

    with pytest.raises(SystemExit):
        cli.main(["--transport", "streamable-http"])


def test_main_accepts_explicit_experimental_streamable_http_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}

    class DummyServer:
        def run(self, transport: str) -> None:
            observed["transport"] = transport

    def create_dummy_server(**kwargs: object) -> DummyServer:
        observed["kwargs"] = kwargs
        return DummyServer()

    monkeypatch.setattr(cli, "create_server", create_dummy_server)

    assert cli.main(["--transport", "streamable-http", "--experimental-enable-http"]) == 0
    assert observed["transport"] == "streamable-http"
    assert observed["kwargs"] == {
        "host": "127.0.0.1",
        "port": 8000,
        "http_bearer_token": None,
        "http_public_url": None,
    }


def test_main_passes_internal_http_options(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: dict[str, object] = {}

    class DummyServer:
        def run(self, transport: str) -> None:
            observed["transport"] = transport

    def create_dummy_server(**kwargs: object) -> DummyServer:
        observed["kwargs"] = kwargs
        return DummyServer()

    monkeypatch.setattr(cli, "create_server", create_dummy_server)
    monkeypatch.setenv("PYSLANG_MCP_HTTP_BEARER_TOKEN", "test-token")

    assert (
        cli.main(
            [
                "--transport",
                "streamable-http",
                "--experimental-enable-http",
                "--http-host",
                "0.0.0.0",
                "--http-port",
                "8765",
                "--http-public-url",
                "http://mcp.example.internal:8765",
                "--http-require-bearer-token",
            ]
        )
        == 0
    )
    assert observed["transport"] == "streamable-http"
    assert observed["kwargs"] == {
        "host": "0.0.0.0",
        "port": 8765,
        "http_bearer_token": "test-token",
        "http_public_url": "http://mcp.example.internal:8765",
    }


def test_main_rejects_required_missing_http_token(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyServer:
        def run(self, transport: str) -> None:  # pragma: no cover
            raise AssertionError(f"unexpected transport: {transport}")

    monkeypatch.setattr(cli, "create_server", lambda **_kwargs: DummyServer())
    monkeypatch.delenv("PYSLANG_MCP_HTTP_BEARER_TOKEN", raising=False)

    with pytest.raises(SystemExit):
        cli.main(
            [
                "--transport",
                "streamable-http",
                "--experimental-enable-http",
                "--http-require-bearer-token",
            ]
        )


def test_main_rejects_unknown_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyServer:
        def run(self, transport: str) -> None:  # pragma: no cover
            raise AssertionError(f"unexpected transport: {transport}")

    monkeypatch.setattr(cli, "create_server", lambda **_kwargs: DummyServer())

    with pytest.raises(SystemExit):
        cli.main(["--transport", "sse"])
