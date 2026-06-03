from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path
from typing import Any, cast

import jsonschema
import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import CallToolResult, Tool

from pyslang_mcp.server import PUBLIC_TOOL_NAMES

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures"

EXPECTED_RESULT_MODELS = {
    PUBLIC_TOOL_NAMES["parse_files"]: "ParseFilesResult",
    PUBLIC_TOOL_NAMES["parse_filelist"]: "ParseFilelistResult",
    PUBLIC_TOOL_NAMES["get_diagnostics"]: "DiagnosticsResult",
    PUBLIC_TOOL_NAMES["list_design_units"]: "ListDesignUnitsResult",
    PUBLIC_TOOL_NAMES["describe_design_unit"]: "DescribeDesignUnitResult",
    PUBLIC_TOOL_NAMES["get_hierarchy"]: "HierarchyResult",
    PUBLIC_TOOL_NAMES["find_symbol"]: "FindSymbolResult",
    PUBLIC_TOOL_NAMES["dump_syntax_tree_summary"]: "SyntaxTreeSummaryResult",
    PUBLIC_TOOL_NAMES["preprocess_files"]: "PreprocessFilesResult",
    PUBLIC_TOOL_NAMES["get_project_summary"]: "ProjectSummaryResult",
}


@pytest.mark.security
def test_mcp_stdio_protocol_smoke() -> None:
    asyncio.run(_run_stdio_protocol_smoke())


async def _run_stdio_protocol_smoke() -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "pyslang_mcp", "--transport", "stdio"],
        cwd=REPO_ROOT,
    )

    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as stderr:
        async with stdio_client(params, errlog=stderr) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools_result = await session.list_tools()
                tools = {tool.name: tool for tool in tools_result.tools}

                _assert_tools_contract(tools)
                await _assert_all_public_tools_call_successfully(session, tools)
                await _assert_structured_errors(session, tools)

        stderr.seek(0)
        assert "Traceback" not in stderr.read()


def _assert_tools_contract(tools: dict[str, Tool]) -> None:
    assert set(tools) == set(EXPECTED_RESULT_MODELS)

    for tool_name, result_model in EXPECTED_RESULT_MODELS.items():
        tool = tools[tool_name]
        annotations = tool.annotations
        assert annotations is not None
        assert annotations.readOnlyHint is True
        assert annotations.destructiveHint is False
        assert annotations.idempotentHint is True
        assert annotations.openWorldHint is False

        output_schema = tool.outputSchema
        assert output_schema is not None
        result_schema = cast(dict[str, Any], output_schema["properties"]["result"])
        result_refs = [
            cast(str, entry["$ref"]) for entry in cast(list[dict[str, Any]], result_schema["anyOf"])
        ]
        assert any(ref.endswith(result_model) for ref in result_refs)
        assert any(ref.endswith("ToolErrorResult") for ref in result_refs)


async def _assert_all_public_tools_call_successfully(
    session: ClientSession,
    tools: dict[str, Tool],
) -> None:
    fixture_root = FIXTURES / "multi_file"
    filelist_args: dict[str, Any] = {
        "project_root": str(fixture_root),
        "filelist": "project.f",
    }
    tool_calls: list[tuple[str, dict[str, Any]]] = [
        (
            PUBLIC_TOOL_NAMES["parse_files"],
            {
                "project_root": str(fixture_root),
                "files": ["pkg.sv", "child.sv", "top.sv"],
                "include_dirs": ["include"],
                "defines": {"WIDTH": "8"},
            },
        ),
        (PUBLIC_TOOL_NAMES["parse_filelist"], filelist_args),
        (PUBLIC_TOOL_NAMES["get_diagnostics"], {**filelist_args, "max_items": 5}),
        (PUBLIC_TOOL_NAMES["list_design_units"], {**filelist_args, "max_items": 10}),
        (PUBLIC_TOOL_NAMES["describe_design_unit"], {**filelist_args, "name": "top"}),
        (
            PUBLIC_TOOL_NAMES["get_hierarchy"],
            {**filelist_args, "max_depth": 4, "max_children": 10},
        ),
        (
            PUBLIC_TOOL_NAMES["find_symbol"],
            {
                **filelist_args,
                "query": "payload",
                "match_mode": "exact",
                "include_references": True,
                "max_results": 5,
            },
        ),
        (
            PUBLIC_TOOL_NAMES["dump_syntax_tree_summary"],
            {**filelist_args, "max_files": 5, "max_node_kinds": 10},
        ),
        (
            PUBLIC_TOOL_NAMES["preprocess_files"],
            {**filelist_args, "max_files": 5, "max_excerpt_lines": 3},
        ),
        (
            PUBLIC_TOOL_NAMES["get_project_summary"],
            {
                **filelist_args,
                "max_diagnostics": 5,
                "max_design_units": 10,
                "max_depth": 4,
                "max_children": 10,
            },
        ),
    ]

    payloads: dict[str, dict[str, Any]] = {}
    for tool_name, arguments in tool_calls:
        result = await session.call_tool(tool_name, arguments)
        assert isinstance(result, CallToolResult)
        assert result.isError is False
        _validate_structured_content(result, tools[tool_name])
        payloads[tool_name] = _result_payload(result)

    assert payloads[PUBLIC_TOOL_NAMES["parse_files"]]["parse"]["file_count"] == 3
    assert payloads[PUBLIC_TOOL_NAMES["parse_filelist"]]["filelist"]["filelists"] == [
        "project.f",
        "rtl.f",
    ]
    assert payloads[PUBLIC_TOOL_NAMES["get_diagnostics"]]["summary"]["total"] == 0
    design_units = payloads[PUBLIC_TOOL_NAMES["list_design_units"]]["design_units"]
    assert {"top", "child", "types_pkg"} <= {unit["name"] for unit in design_units}
    assert payloads[PUBLIC_TOOL_NAMES["describe_design_unit"]]["found"] is True
    assert payloads[PUBLIC_TOOL_NAMES["get_hierarchy"]]["summary"]["total_instances"] == 2
    assert payloads[PUBLIC_TOOL_NAMES["find_symbol"]]["summary"]["declaration_count"] >= 1
    assert payloads[PUBLIC_TOOL_NAMES["find_symbol"]]["summary"]["reference_count"] >= 1
    assert payloads[PUBLIC_TOOL_NAMES["dump_syntax_tree_summary"]]["summary"]["file_count"] == 3
    assert payloads[PUBLIC_TOOL_NAMES["preprocess_files"]]["mode"] == "summary_only"
    assert payloads[PUBLIC_TOOL_NAMES["get_project_summary"]]["summary"]["file_count"] == 3


async def _assert_structured_errors(
    session: ClientSession,
    tools: dict[str, Tool],
) -> None:
    fixture_root = FIXTURES / "multi_file"
    invalid_calls: list[tuple[str, dict[str, Any], str]] = [
        (
            PUBLIC_TOOL_NAMES["get_diagnostics"],
            {
                "project_root": str(fixture_root),
                "files": ["top.sv"],
                "filelist": "project.f",
            },
            "invalid_arguments",
        ),
        (
            PUBLIC_TOOL_NAMES["parse_files"],
            {
                "project_root": str(fixture_root),
                "files": [str(REPO_ROOT / "pyproject.toml")],
            },
            "path_outside_root",
        ),
        (
            PUBLIC_TOOL_NAMES["parse_filelist"],
            {
                "project_root": str(fixture_root),
                "filelist": str(REPO_ROOT / "pyproject.toml"),
            },
            "path_outside_root",
        ),
    ]

    for tool_name, arguments, expected_code in invalid_calls:
        result = await session.call_tool(tool_name, arguments)
        assert isinstance(result, CallToolResult)
        assert result.isError is True
        _validate_structured_content(result, tools[tool_name])
        payload = _result_payload(result)
        assert payload["error"]["code"] == expected_code
        assert payload["error"]["message"]
        assert payload["error"]["hint"]


def _validate_structured_content(result: CallToolResult, tool: Tool) -> None:
    assert result.structuredContent is not None
    assert tool.outputSchema is not None
    jsonschema.validate(instance=result.structuredContent, schema=tool.outputSchema)


def _result_payload(result: CallToolResult) -> dict[str, Any]:
    structured = cast(dict[str, Any], result.structuredContent)
    assert set(structured) == {"result"}
    return cast(dict[str, Any], structured["result"])
