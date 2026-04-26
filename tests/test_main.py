from __future__ import annotations

import pytest

import pyslang_mcp.__main__ as cli


def test_main_runs_default_stdio_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: dict[str, str] = {}

    class DummyServer:
        def run(self, transport: str) -> None:
            observed["transport"] = transport

    monkeypatch.setattr(cli, "create_server", lambda: DummyServer())

    assert cli.main([]) == 0
    assert observed["transport"] == "stdio"


def test_main_rejects_streamable_http_without_experimental_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DummyServer:
        def run(self, transport: str) -> None:  # pragma: no cover
            raise AssertionError(f"unexpected transport: {transport}")

    monkeypatch.setattr(cli, "create_server", lambda: DummyServer())

    with pytest.raises(SystemExit):
        cli.main(["--transport", "streamable-http"])


def test_main_accepts_explicit_experimental_streamable_http_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, str] = {}

    class DummyServer:
        def run(self, transport: str) -> None:
            observed["transport"] = transport

    monkeypatch.setattr(cli, "create_server", lambda: DummyServer())

    assert cli.main(["--transport", "streamable-http", "--experimental-enable-http"]) == 0
    assert observed["transport"] == "streamable-http"


def test_main_rejects_unknown_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyServer:
        def run(self, transport: str) -> None:  # pragma: no cover
            raise AssertionError(f"unexpected transport: {transport}")

    monkeypatch.setattr(cli, "create_server", lambda: DummyServer())

    with pytest.raises(SystemExit):
        cli.main(["--transport", "sse"])
