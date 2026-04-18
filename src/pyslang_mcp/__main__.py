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
        choices=("stdio", "sse", "streamable-http"),
        default="stdio",
        help="MCP transport to use. stdio is the default and intended first transport.",
    )
    args = parser.parse_args(argv)
    create_server().run(args.transport)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
