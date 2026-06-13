from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, cast

import pytest
from mcp.types import CallToolResult

import pyslang_mcp.server as server_module
from pyslang_mcp.cache import AnalysisCache
from pyslang_mcp.server import (
    MAX_ASSIGNMENT_RESULTS,
    MAX_DIAGNOSTIC_EXAMPLES_PER_GROUP,
    MAX_DIAGNOSTIC_GROUPS,
    MAX_EXCERPT_LINES,
    MAX_CONNECTION_RESULTS,
    MAX_HIERARCHY_CHILDREN,
    MAX_HIERARCHY_DEPTH,
    MAX_LIST_ITEMS,
    MAX_MEMBER_RESULTS,
    MAX_NODE_KINDS,
    MAX_SUMMARY_FILES,
    MAX_SYMBOL_RESULTS,
    MAX_TRACE_DEPTH,
    MAX_TRACE_EDGES,
    PUBLIC_TOOL_NAMES,
    create_server,
)

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
        PUBLIC_TOOL_NAMES["summarize_diagnostics_by_code"]: "SummarizeDiagnosticsByCodeResult",
        PUBLIC_TOOL_NAMES["list_design_units"]: "ListDesignUnitsResult",
        PUBLIC_TOOL_NAMES["describe_design_unit"]: "DescribeDesignUnitResult",
        PUBLIC_TOOL_NAMES["find_member"]: "FindMemberResult",
        PUBLIC_TOOL_NAMES["get_assignments"]: "GetAssignmentsResult",
        PUBLIC_TOOL_NAMES["trace_connectivity"]: "TraceConnectivityResult",
        PUBLIC_TOOL_NAMES["get_hierarchy"]: "HierarchyResult",
        PUBLIC_TOOL_NAMES["get_instance_connections"]: "GetInstanceConnectionsResult",
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


@pytest.mark.security
def test_tools_list_exposes_hard_limit_bounds() -> None:
    server = create_server(cache=AnalysisCache())

    async def run() -> dict[str, dict[str, Any]]:
        tools = await server.list_tools()
        return {tool.name: cast(dict[str, Any], tool.inputSchema) for tool in tools}

    input_schemas = asyncio.run(run())
    expected_bounds = [
        (PUBLIC_TOOL_NAMES["get_diagnostics"], "max_items", 0, MAX_LIST_ITEMS),
        (
            PUBLIC_TOOL_NAMES["summarize_diagnostics_by_code"],
            "max_groups",
            0,
            MAX_DIAGNOSTIC_GROUPS,
        ),
        (
            PUBLIC_TOOL_NAMES["summarize_diagnostics_by_code"],
            "max_examples_per_group",
            0,
            MAX_DIAGNOSTIC_EXAMPLES_PER_GROUP,
        ),
        (PUBLIC_TOOL_NAMES["list_design_units"], "max_items", 0, MAX_LIST_ITEMS),
        (PUBLIC_TOOL_NAMES["get_hierarchy"], "max_depth", 1, MAX_HIERARCHY_DEPTH),
        (PUBLIC_TOOL_NAMES["get_hierarchy"], "max_children", 0, MAX_HIERARCHY_CHILDREN),
        (
            PUBLIC_TOOL_NAMES["get_instance_connections"],
            "max_connections",
            0,
            MAX_CONNECTION_RESULTS,
        ),
        (PUBLIC_TOOL_NAMES["find_member"], "max_results", 0, MAX_MEMBER_RESULTS),
        (PUBLIC_TOOL_NAMES["get_assignments"], "max_results", 0, MAX_ASSIGNMENT_RESULTS),
        (PUBLIC_TOOL_NAMES["trace_connectivity"], "max_depth", 1, MAX_TRACE_DEPTH),
        (PUBLIC_TOOL_NAMES["trace_connectivity"], "max_edges", 0, MAX_TRACE_EDGES),
        (PUBLIC_TOOL_NAMES["find_symbol"], "max_results", 0, MAX_SYMBOL_RESULTS),
        (PUBLIC_TOOL_NAMES["dump_syntax_tree_summary"], "max_files", 0, MAX_SUMMARY_FILES),
        (PUBLIC_TOOL_NAMES["dump_syntax_tree_summary"], "max_node_kinds", 0, MAX_NODE_KINDS),
        (PUBLIC_TOOL_NAMES["preprocess_files"], "max_files", 0, MAX_SUMMARY_FILES),
        (PUBLIC_TOOL_NAMES["preprocess_files"], "max_excerpt_lines", 0, MAX_EXCERPT_LINES),
        (PUBLIC_TOOL_NAMES["get_project_summary"], "max_diagnostics", 0, MAX_LIST_ITEMS),
        (PUBLIC_TOOL_NAMES["get_project_summary"], "max_design_units", 0, MAX_LIST_ITEMS),
        (PUBLIC_TOOL_NAMES["get_project_summary"], "max_depth", 1, MAX_HIERARCHY_DEPTH),
        (PUBLIC_TOOL_NAMES["get_project_summary"], "max_children", 0, MAX_HIERARCHY_CHILDREN),
    ]
    for tool_name, argument_name, expected_minimum, expected_maximum in expected_bounds:
        schema = input_schemas[tool_name]["properties"][argument_name]
        assert schema["minimum"] == expected_minimum
        assert schema["maximum"] == expected_maximum


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


def test_summarize_diagnostics_by_code_tool() -> None:
    payload, is_error = _call_tool_json(
        PUBLIC_TOOL_NAMES["summarize_diagnostics_by_code"],
        {
            "project_root": str(FIXTURES / "broken"),
            "files": ["broken.sv"],
            "max_groups": 10,
            "max_examples_per_group": 1,
        },
    )

    assert not is_error
    assert payload["summary"]["total_diagnostics"] == 1
    assert payload["groups"][0]["count"] == 1


def test_find_member_tool() -> None:
    payload, is_error = _call_tool_json(
        PUBLIC_TOOL_NAMES["find_member"],
        {
            "project_root": str(FIXTURES / "verilog_debug"),
            "filelist": "project.f",
            "top_modules": ["debug_top"],
            "design_unit": "debug_stage",
            "query": "response_pop_fifo__rdy",
            "match_mode": "exact",
            "max_results": 5,
        },
    )

    assert not is_error
    assert payload["found_design_unit"] is True
    assert payload["summary"]["total"] == 1
    assert payload["members"][0]["name"] == "response_pop_fifo__rdy"


def test_get_instance_connections_tool() -> None:
    payload, is_error = _call_tool_json(
        PUBLIC_TOOL_NAMES["get_instance_connections"],
        {
            "project_root": str(FIXTURES / "verilog_debug"),
            "filelist": "project.f",
            "top_modules": ["debug_top"],
            "instance_path_or_name": "debug_top.u_stage",
            "max_connections": 10,
        },
    )

    assert not is_error
    assert payload["found"] is True
    assert payload["summary"]["total"] == 6


def test_get_assignments_tool() -> None:
    payload, is_error = _call_tool_json(
        PUBLIC_TOOL_NAMES["get_assignments"],
        {
            "project_root": str(FIXTURES / "verilog_debug"),
            "filelist": "project.f",
            "top_modules": ["debug_top"],
            "design_unit": "debug_stage",
            "signal": "response__vld",
            "role": "lhs",
            "max_results": 5,
        },
    )

    assert not is_error
    assert payload["summary"]["total"] == 1
    assert payload["assignments"][0]["lhs_snippet"] == "response__vld"


def test_trace_connectivity_tool() -> None:
    payload, is_error = _call_tool_json(
        PUBLIC_TOOL_NAMES["trace_connectivity"],
        {
            "project_root": str(FIXTURES / "verilog_debug"),
            "filelist": "project.f",
            "top_modules": ["debug_top"],
            "start": "debug_top.ctrl_out__rdy",
            "direction": "load",
            "max_depth": 5,
            "max_edges": 20,
        },
    )

    assert not is_error
    assert "debug_top.ctrl_out__rdy" in payload["resolved_starts"]
    assert payload["summary"]["path_count"] >= 1


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


@pytest.mark.parametrize(
    (
        "tool_name",
        "argument_name",
        "too_large_value",
        "extra_arguments",
        "fixture_name",
    ),
    [
        (PUBLIC_TOOL_NAMES["get_diagnostics"], "max_items", MAX_LIST_ITEMS + 1, {}, "multi_file"),
        (
            PUBLIC_TOOL_NAMES["summarize_diagnostics_by_code"],
            "max_groups",
            MAX_DIAGNOSTIC_GROUPS + 1,
            {},
            "multi_file",
        ),
        (
            PUBLIC_TOOL_NAMES["summarize_diagnostics_by_code"],
            "max_examples_per_group",
            MAX_DIAGNOSTIC_EXAMPLES_PER_GROUP + 1,
            {},
            "multi_file",
        ),
        (
            PUBLIC_TOOL_NAMES["list_design_units"],
            "max_items",
            MAX_LIST_ITEMS + 1,
            {},
            "multi_file",
        ),
        (
            PUBLIC_TOOL_NAMES["get_hierarchy"],
            "max_depth",
            MAX_HIERARCHY_DEPTH + 1,
            {},
            "multi_file",
        ),
        (
            PUBLIC_TOOL_NAMES["get_hierarchy"],
            "max_children",
            MAX_HIERARCHY_CHILDREN + 1,
            {},
            "multi_file",
        ),
        (
            PUBLIC_TOOL_NAMES["find_member"],
            "max_results",
            MAX_MEMBER_RESULTS + 1,
            {"design_unit": "debug_stage", "query": "response__vld"},
            "verilog_debug",
        ),
        (
            PUBLIC_TOOL_NAMES["get_assignments"],
            "max_results",
            MAX_ASSIGNMENT_RESULTS + 1,
            {"design_unit": "debug_stage", "signal": "response__vld"},
            "verilog_debug",
        ),
        (
            PUBLIC_TOOL_NAMES["get_instance_connections"],
            "max_connections",
            MAX_CONNECTION_RESULTS + 1,
            {"instance_path_or_name": "debug_top.u_stage"},
            "verilog_debug",
        ),
        (
            PUBLIC_TOOL_NAMES["trace_connectivity"],
            "max_depth",
            MAX_TRACE_DEPTH + 1,
            {"start": "debug_top.ctrl_out__rdy"},
            "verilog_debug",
        ),
        (
            PUBLIC_TOOL_NAMES["trace_connectivity"],
            "max_edges",
            MAX_TRACE_EDGES + 1,
            {"start": "debug_top.ctrl_out__rdy"},
            "verilog_debug",
        ),
        (
            PUBLIC_TOOL_NAMES["find_symbol"],
            "max_results",
            MAX_SYMBOL_RESULTS + 1,
            {"query": "payload"},
            "multi_file",
        ),
        (
            PUBLIC_TOOL_NAMES["dump_syntax_tree_summary"],
            "max_files",
            MAX_SUMMARY_FILES + 1,
            {},
            "multi_file",
        ),
        (
            PUBLIC_TOOL_NAMES["dump_syntax_tree_summary"],
            "max_node_kinds",
            MAX_NODE_KINDS + 1,
            {},
            "multi_file",
        ),
        (
            PUBLIC_TOOL_NAMES["preprocess_files"],
            "max_files",
            MAX_SUMMARY_FILES + 1,
            {},
            "multi_file",
        ),
        (
            PUBLIC_TOOL_NAMES["preprocess_files"],
            "max_excerpt_lines",
            MAX_EXCERPT_LINES + 1,
            {},
            "multi_file",
        ),
        (
            PUBLIC_TOOL_NAMES["get_project_summary"],
            "max_diagnostics",
            MAX_LIST_ITEMS + 1,
            {},
            "multi_file",
        ),
        (
            PUBLIC_TOOL_NAMES["get_project_summary"],
            "max_design_units",
            MAX_LIST_ITEMS + 1,
            {},
            "multi_file",
        ),
        (
            PUBLIC_TOOL_NAMES["get_project_summary"],
            "max_depth",
            MAX_HIERARCHY_DEPTH + 1,
            {},
            "multi_file",
        ),
        (
            PUBLIC_TOOL_NAMES["get_project_summary"],
            "max_children",
            MAX_HIERARCHY_CHILDREN + 1,
            {},
            "multi_file",
        ),
    ],
)
@pytest.mark.security
def test_limit_out_of_range_returns_structured_tool_error(
    tool_name: str,
    argument_name: str,
    too_large_value: int,
    extra_arguments: dict[str, object],
    fixture_name: str,
) -> None:
    payload, is_error = _call_tool_json(
        tool_name,
        {
            "project_root": str(FIXTURES / fixture_name),
            "filelist": "project.f",
            **({"top_modules": ["debug_top"]} if fixture_name == "verilog_debug" else {}),
            **extra_arguments,
            argument_name: too_large_value,
        },
    )

    assert is_error
    assert payload["error"]["code"] == "invalid_arguments"
    assert argument_name in payload["error"]["message"]


def test_invalid_assignment_role_returns_structured_tool_error() -> None:
    payload, is_error = _call_tool_json(
        PUBLIC_TOOL_NAMES["get_assignments"],
        {
            "project_root": str(FIXTURES / "verilog_debug"),
            "filelist": "project.f",
            "top_modules": ["debug_top"],
            "design_unit": "debug_stage",
            "signal": "response__vld",
            "role": "driver",
        },
    )

    assert is_error
    assert payload["error"]["code"] == "invalid_arguments"
    assert "role" in payload["error"]["message"]


def test_invalid_trace_direction_returns_structured_tool_error() -> None:
    payload, is_error = _call_tool_json(
        PUBLIC_TOOL_NAMES["trace_connectivity"],
        {
            "project_root": str(FIXTURES / "verilog_debug"),
            "filelist": "project.f",
            "top_modules": ["debug_top"],
            "start": "debug_top.ctrl_out__rdy",
            "direction": "fanin",
        },
    )

    assert is_error
    assert payload["error"]["code"] == "invalid_arguments"
    assert "direction" in payload["error"]["message"]


def test_identical_new_tool_calls_reuse_cached_tool_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    original_find_member = server_module.find_member_core

    def counted_find_member(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return cast(dict[str, Any], original_find_member(*args, **kwargs))

    monkeypatch.setattr(server_module, "find_member_core", counted_find_member)
    server = create_server(cache=AnalysisCache())
    arguments = {
        "project_root": str(FIXTURES / "verilog_debug"),
        "filelist": "project.f",
        "top_modules": ["debug_top"],
        "design_unit": "debug_stage",
        "query": "response__vld",
        "match_mode": "exact",
    }

    async def run() -> None:
        first = await server.call_tool(PUBLIC_TOOL_NAMES["find_member"], arguments)
        second = await server.call_tool(PUBLIC_TOOL_NAMES["find_member"], arguments)
        assert isinstance(first, CallToolResult)
        assert isinstance(second, CallToolResult)
        assert first.structuredContent == second.structuredContent

    asyncio.run(run())

    assert calls == 1


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
