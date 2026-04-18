from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, cast

from mcp.types import ContentBlock, TextContent

from pyslang_mcp.server import create_server

FIXTURES = Path(__file__).parent / "fixtures"


def _call_tool_json(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    server = create_server()

    async def run() -> dict[str, Any]:
        result = await server.call_tool(tool_name, arguments)
        if isinstance(result, tuple):
            content_blocks_raw, structured_raw = result
            content_blocks = cast(list[ContentBlock], content_blocks_raw)
            structured = cast(dict[str, Any], structured_raw)
            assert content_blocks
            content = cast(TextContent, content_blocks[0])
            assert isinstance(content, TextContent)
            assert json.loads(content.text) == structured
            return structured
        content_blocks = cast(list[ContentBlock], result)
        assert len(content_blocks) == 1
        content = cast(TextContent, content_blocks[0])
        assert isinstance(content, TextContent)
        return cast(dict[str, Any], json.loads(content.text))

    return asyncio.run(run())


def test_parse_filelist_tool() -> None:
    payload = _call_tool_json(
        "parse_filelist",
        {
            "project_root": str(FIXTURES / "multi_file"),
            "filelist": "project.f",
        },
    )

    assert payload["parse"]["file_count"] == 3
    assert payload["filelist"]["filelists"] == ["project.f", "rtl.f"]


def test_get_hierarchy_tool() -> None:
    payload = _call_tool_json(
        "get_hierarchy",
        {
            "project_root": str(FIXTURES / "multi_file"),
            "filelist": "project.f",
        },
    )

    assert payload["summary"]["total_instances"] == 2
    assert payload["hierarchy"][0]["children"][0]["name"] == "u_child"
