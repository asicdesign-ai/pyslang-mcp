from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, cast

from mcp.types import CallToolResult

from pyslang_mcp.cache import AnalysisCache
from pyslang_mcp.server import PUBLIC_TOOL_NAMES, create_server

FIXTURES = Path(__file__).parent / "fixtures"


def _call_tool_json(tool_name: str, arguments: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    server = create_server(cache=AnalysisCache())

    async def run() -> tuple[dict[str, Any], bool]:
        result = await server.call_tool(tool_name, arguments)
        assert isinstance(result, CallToolResult)
        assert result.structuredContent is not None
        structured = cast(dict[str, Any], result.structuredContent)
        if "result" in structured and isinstance(structured["result"], dict):
            return cast(dict[str, Any], structured["result"]), bool(result.isError)
        return structured, bool(result.isError)

    return asyncio.run(run())


def test_tools_list_exposes_output_schema() -> None:
    server = create_server(cache=AnalysisCache())
    expected_result_models = {
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

    async def run() -> dict[str, dict[str, Any]]:
        tools = await server.list_tools()
        tool_map = {tool.name: tool for tool in tools}
        assert set(tool_map) == set(expected_result_models)

        schemas: dict[str, dict[str, Any]] = {}
        for tool_name in expected_result_models:
            output_schema = tool_map[tool_name].outputSchema
            assert output_schema is not None
            schemas[tool_name] = cast(dict[str, Any], output_schema)
        return schemas

    output_schemas = asyncio.run(run())
    for tool_name, model_name in expected_result_models.items():
        output_schema = output_schemas[tool_name]
        assert "result" in output_schema["properties"]
        result_schema = output_schema["properties"]["result"]
        assert any(entry["$ref"].endswith(model_name) for entry in result_schema["anyOf"])


def test_parse_filelist_tool() -> None:
    payload, is_error = _call_tool_json(
        PUBLIC_TOOL_NAMES["parse_filelist"],
        {
            "project_root": str(FIXTURES / "multi_file"),
            "filelist": "project.f",
        },
    )

    assert not is_error
    assert payload["parse"]["file_count"] == 3
    assert payload["filelist"]["filelists"] == ["project.f", "rtl.f"]


def test_get_hierarchy_tool() -> None:
    payload, is_error = _call_tool_json(
        PUBLIC_TOOL_NAMES["get_hierarchy"],
        {
            "project_root": str(FIXTURES / "multi_file"),
            "filelist": "project.f",
        },
    )

    assert not is_error
    assert payload["summary"]["total_instances"] == 2
    assert payload["hierarchy"][0]["children"][0]["name"] == "u_child"


def test_describe_design_unit_not_found_is_not_a_protocol_error() -> None:
    payload, is_error = _call_tool_json(
        PUBLIC_TOOL_NAMES["describe_design_unit"],
        {
            "project_root": str(FIXTURES / "multi_file"),
            "filelist": "project.f",
            "name": "missing_top",
        },
    )

    assert not is_error
    assert payload["found"] is False
    assert payload["design_unit"] is None


def test_invalid_argument_combo_returns_structured_tool_error() -> None:
    payload, is_error = _call_tool_json(
        PUBLIC_TOOL_NAMES["get_diagnostics"],
        {
            "project_root": str(FIXTURES / "multi_file"),
            "files": ["top.sv"],
            "filelist": "project.f",
        },
    )

    assert is_error
    assert payload["error"]["code"] == "invalid_arguments"
