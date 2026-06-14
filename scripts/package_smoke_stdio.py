from __future__ import annotations

import argparse
import asyncio
import tempfile
from pathlib import Path
from typing import Any, cast

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import CallToolResult

from pyslang_mcp.server import PUBLIC_TOOL_NAMES

EXPECTED_TOOL_NAMES = set(PUBLIC_TOOL_NAMES.values())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smoke-test an installed pyslang-mcp console script over stdio."
    )
    parser.add_argument(
        "server_command",
        help="Path to the installed pyslang-mcp console script.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        required=True,
        help="Path to the multi_file fixture project root.",
    )
    args = parser.parse_args()

    asyncio.run(_run_stdio_smoke(args.server_command, args.project_root.resolve()))
    return 0


async def _run_stdio_smoke(server_command: str, project_root: Path) -> None:
    params = StdioServerParameters(
        command=server_command,
        args=["--transport", "stdio"],
    )

    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as stderr:
        async with stdio_client(params, errlog=stderr) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()

                tools_result = await session.list_tools()
                tool_names = {tool.name for tool in tools_result.tools}
                missing_tools = EXPECTED_TOOL_NAMES - tool_names
                extra_tools = tool_names - EXPECTED_TOOL_NAMES
                if missing_tools or extra_tools:
                    raise AssertionError(
                        f"unexpected tool set: missing={sorted(missing_tools)}, "
                        f"extra={sorted(extra_tools)}"
                    )

                result = await session.call_tool(
                    "pyslang_parse_filelist",
                    {
                        "project_root": str(project_root),
                        "filelist": "project.f",
                    },
                )
                payload = _result_payload(result)
                if result.isError:
                    raise AssertionError(f"parse_filelist returned tool error: {payload!r}")
                if payload["parse"]["file_count"] != 3:
                    raise AssertionError(f"unexpected parse payload: {payload!r}")
                if payload["filelist"]["filelists"] != ["project.f", "rtl.f"]:
                    raise AssertionError(f"unexpected filelist payload: {payload!r}")

        stderr.seek(0)
        stderr_text = stderr.read()
        if "Traceback" in stderr_text:
            raise AssertionError(f"server stderr contained traceback:\n{stderr_text}")


def _result_payload(result: CallToolResult) -> dict[str, Any]:
    structured = result.structuredContent
    if not isinstance(structured, dict):
        raise AssertionError(f"missing structured content: {structured!r}")
    result_payload = structured.get("result")
    if not isinstance(result_payload, dict):
        raise AssertionError(f"missing result payload: {structured!r}")
    return cast(dict[str, Any], result_payload)


if __name__ == "__main__":
    raise SystemExit(main())
