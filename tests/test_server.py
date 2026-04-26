from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, cast

import pytest
from mcp.types import CallToolResult

import pyslang_mcp.server as server_module
from pyslang_mcp.cache import AnalysisCache
from pyslang_mcp.server import MAX_LIST_ITEMS, MAX_SYMBOL_RESULTS, PUBLIC_TOOL_NAMES, create_server

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


def test_tools_list_exposes_hard_limit_bounds() -> None:
    server = create_server(cache=AnalysisCache())

    async def run() -> dict[str, dict[str, Any]]:
        tools = await server.list_tools()
        return {tool.name: cast(dict[str, Any], tool.inputSchema) for tool in tools}

    input_schemas = asyncio.run(run())
    assert (
        input_schemas[PUBLIC_TOOL_NAMES["get_diagnostics"]]["properties"]["max_items"]["maximum"]
        == MAX_LIST_ITEMS
    )
    assert (
        input_schemas[PUBLIC_TOOL_NAMES["find_symbol"]]["properties"]["max_results"]["maximum"]
        == MAX_SYMBOL_RESULTS
    )


def test_parse_filelist_tool() -> None:
    payload, is_error = _call_tool_json(
        PUBLIC_TOOL_NAMES["parse_filelist"],
        {
            "project_root": str(FIXTURES / "multi_file"),
            "filelist": "project.f",
        },
    )

    assert not is_error
    assert payload["project_status"]["status"] == "ok"
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


def test_identical_tool_calls_reuse_cached_tool_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    original_find_symbol = server_module.find_symbol_core

    def counted_find_symbol(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return cast(dict[str, Any], original_find_symbol(*args, **kwargs))

    monkeypatch.setattr(server_module, "find_symbol_core", counted_find_symbol)
    server = create_server(cache=AnalysisCache())
    arguments = {
        "project_root": str(FIXTURES / "multi_file"),
        "filelist": "project.f",
        "query": "payload",
        "match_mode": "exact",
        "include_references": True,
    }

    async def run() -> None:
        first = await server.call_tool(PUBLIC_TOOL_NAMES["find_symbol"], arguments)
        second = await server.call_tool(PUBLIC_TOOL_NAMES["find_symbol"], arguments)
        assert isinstance(first, CallToolResult)
        assert isinstance(second, CallToolResult)
        assert first.structuredContent == second.structuredContent

    asyncio.run(run())

    assert calls == 1


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


def test_invalid_match_mode_returns_structured_tool_error() -> None:
    payload, is_error = _call_tool_json(
        PUBLIC_TOOL_NAMES["find_symbol"],
        {
            "project_root": str(FIXTURES / "multi_file"),
            "filelist": "project.f",
            "query": "top",
            "match_mode": "regex",
        },
    )

    assert is_error
    assert payload["error"]["code"] == "invalid_arguments"
    assert "match_mode" in payload["error"]["message"]


def test_limit_out_of_range_returns_structured_tool_error() -> None:
    payload, is_error = _call_tool_json(
        PUBLIC_TOOL_NAMES["get_diagnostics"],
        {
            "project_root": str(FIXTURES / "multi_file"),
            "filelist": "project.f",
            "max_items": MAX_LIST_ITEMS + 1,
        },
    )

    assert is_error
    assert payload["error"]["code"] == "invalid_arguments"
    assert "max_items" in payload["error"]["message"]


def test_empty_file_list_returns_structured_project_load_error() -> None:
    payload, is_error = _call_tool_json(
        PUBLIC_TOOL_NAMES["parse_files"],
        {
            "project_root": str(FIXTURES / "multi_file"),
            "files": [],
        },
    )

    assert is_error
    assert payload["error"]["code"] == "project_load_error"


def test_output_schema_failure_returns_structured_tool_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        server_module,
        "get_diagnostics_core",
        lambda *_args, **_kwargs: {"not": "a diagnostics result"},
    )

    payload, is_error = _call_tool_json(
        PUBLIC_TOOL_NAMES["get_diagnostics"],
        {
            "project_root": str(FIXTURES / "multi_file"),
            "filelist": "project.f",
        },
    )

    assert is_error
    assert payload["error"]["code"] == "internal_schema_error"
    assert payload["error"]["details"]["error_count"] > 0


def test_unexpected_analysis_failure_returns_structured_tool_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_runtime_error(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("synthetic pyslang failure")

    monkeypatch.setattr(server_module, "build_analysis", raise_runtime_error)

    payload, is_error = _call_tool_json(
        PUBLIC_TOOL_NAMES["get_diagnostics"],
        {
            "project_root": str(FIXTURES / "multi_file"),
            "filelist": "project.f",
        },
    )

    assert is_error
    assert payload["error"]["code"] == "analysis_error"
    assert payload["error"]["details"] == {"error_type": "RuntimeError"}
