from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from pyslang_mcp.analysis import (
    _format_diagnostic_message,
    build_analysis,
    describe_design_unit,
    dump_syntax_tree_summary,
    find_symbol,
    get_diagnostics,
    get_hierarchy,
    get_project_summary,
    list_design_units,
    preprocess_files,
)
from pyslang_mcp.project_loader import load_project_from_filelist, load_project_from_files

FIXTURES = Path(__file__).parent / "fixtures"


def test_analysis_over_filelist_fixture() -> None:
    project = load_project_from_filelist(
        project_root=FIXTURES / "multi_file",
        filelist="project.f",
    )
    bundle = build_analysis(project)

    diagnostics = get_diagnostics(bundle)
    assert diagnostics["summary"]["total"] == 0

    units = list_design_units(bundle)
    unit_names = {unit["name"] for unit in units["design_units"]}
    assert {"top", "child", "types_pkg"} <= unit_names

    description = describe_design_unit(bundle, name="top")
    assert description["found"] is True
    assert description["design_unit"]["ports"][0]["name"] == "clk"
    assert description["design_unit"]["child_instances"][0]["name"] == "u_child"
    assert "payload" in description["design_unit"]["declared_names"]

    missing_description = describe_design_unit(bundle, name="missing_top")
    assert missing_description["found"] is False
    assert missing_description["design_unit"] is None

    hierarchy = get_hierarchy(bundle)
    assert hierarchy["hierarchy"][0]["name"] == "top"
    assert hierarchy["hierarchy"][0]["children"][0]["name"] == "u_child"

    symbol_hits = find_symbol(bundle, query="payload", include_references=True)
    assert symbol_hits["summary"]["declaration_count"] >= 1
    assert symbol_hits["summary"]["reference_count"] >= 1

    type_hits = find_symbol(bundle, query="data_t", include_references=True)
    assert type_hits["summary"]["declaration_count"] >= 1
    assert type_hits["summary"]["reference_count"] >= 1
    assert any(ref["reference_kind"] == "declared_type" for ref in type_hits["references"])

    package_hits = find_symbol(bundle, query="types_pkg", include_references=True)
    assert package_hits["summary"]["declaration_count"] >= 1
    assert package_hits["summary"]["reference_count"] >= 1
    assert any(ref["reference_kind"] == "package_import" for ref in package_hits["references"])

    module_hits = find_symbol(bundle, query="child", include_references=True)
    assert module_hits["summary"]["declaration_count"] >= 1
    assert module_hits["summary"]["reference_count"] >= 1
    assert any(ref["reference_kind"] == "instance_definition" for ref in module_hits["references"])

    syntax = dump_syntax_tree_summary(bundle)
    assert len(syntax["files"]) == 3
    assert any(file["file"] == "top.sv" for file in syntax["files"])

    preprocessing = preprocess_files(bundle)
    assert preprocessing["mode"] == "summary_only"
    assert preprocessing["effective_defines"] == {"WIDTH": "8"}
    assert preprocessing["files"][0]["include_directives"] == []

    summary = get_project_summary(bundle, max_diagnostics=10, max_design_units=20)
    assert summary["summary"]["file_count"] == 3
    assert summary["limits"]["max_diagnostics"] == 10


def test_diagnostics_on_broken_fixture() -> None:
    project = load_project_from_files(
        project_root=FIXTURES / "broken",
        files=["broken.sv"],
    )
    bundle = build_analysis(project)

    diagnostics = get_diagnostics(bundle)
    assert diagnostics["summary"]["total"] == 1
    assert diagnostics["diagnostics"][0]["severity"] == "error"
    assert "missing_symbol" in diagnostics["diagnostics"][0]["message"]


def test_format_diagnostic_message_preserves_escaped_braces() -> None:
    diagnostic_engine = SimpleNamespace(getMessage=lambda _code: "literal {{}} before {} after")
    bundle = SimpleNamespace(diagnostic_engine=diagnostic_engine)
    diagnostic = SimpleNamespace(code="TEST", args=["payload"])

    message = _format_diagnostic_message(cast(Any, bundle), cast(Any, diagnostic))

    assert message == "literal {} before payload after"
