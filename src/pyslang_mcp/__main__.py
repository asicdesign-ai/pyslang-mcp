"""CLI entrypoint for pyslang-mcp."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from .server import create_server


def main(argv: Sequence[str] | None = None) -> int:
    """Run the MCP server."""

    parser = argparse.ArgumentParser(description="Run the pyslang-mcp server.")
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="stdio",
        help=(
            "MCP transport to use. `stdio` is the default. `streamable-http` is "
            "experimental and requires --experimental-enable-http."
        ),
    )
    parser.add_argument(
        "--experimental-enable-http",
        action="store_true",
        help=(
            "Allow the experimental local streamable-http transport. This mode is not "
            "a hosted deployment and does not add authentication or workspace isolation."
        ),
    )
    args = parser.parse_args(argv)
    if args.transport == "streamable-http" and not args.experimental_enable_http:
        parser.error(
            "`streamable-http` is experimental and requires --experimental-enable-http. "
            "Use the default `stdio` transport for normal local MCP clients."
        )
    create_server().run(args.transport)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
