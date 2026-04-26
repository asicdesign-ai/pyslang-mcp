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
    assert bundle.index is not None
    assert bundle.index.design_unit_records
    assert bundle.index.declarations
    assert bundle.index.references

    diagnostics = get_diagnostics(bundle)
    assert diagnostics["project_status"]["status"] == "ok"
    assert diagnostics["summary"]["total"] == 0

    units = list_design_units(bundle)
    assert units["project_status"]["status"] == "ok"
    unit_names = {unit["name"] for unit in units["design_units"]}
    assert {"top", "child", "types_pkg"} <= unit_names

    description = describe_design_unit(bundle, name="top")
    assert description["project_status"]["status"] == "ok"
    assert description["found"] is True
    assert description["design_unit"]["ports"][0]["name"] == "clk"
    assert description["design_unit"]["child_instances"][0]["name"] == "u_child"
    assert "payload" in description["design_unit"]["declared_names"]
    assert bundle.index.design_unit_description_cache

    missing_description = describe_design_unit(bundle, name="missing_top")
    assert missing_description["found"] is False
    assert missing_description["design_unit"] is None

    hierarchy = get_hierarchy(bundle)
    assert hierarchy["project_status"]["status"] == "ok"
    assert hierarchy["hierarchy"][0]["name"] == "top"
    assert hierarchy["hierarchy"][0]["children"][0]["name"] == "u_child"

    symbol_hits = find_symbol(bundle, query="payload", include_references=True)
    assert symbol_hits["project_status"]["status"] == "ok"
    assert symbol_hits["summary"]["declaration_count"] >= 1
    assert symbol_hits["summary"]["reference_count"] >= 1
    assert find_symbol(bundle, query="payload", include_references=True) == symbol_hits
    limited_symbol_hits = find_symbol(bundle, query="payload", max_results=0)
    assert limited_symbol_hits["summary"]["declaration_count"] >= 1
    assert limited_symbol_hits["summary"]["declaration_truncation"]["returned"] == 0
    assert limited_symbol_hits["summary"]["declaration_truncation"]["truncated"] is True

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
    assert syntax["project_status"]["status"] == "ok"
    assert len(syntax["files"]) == 3
    assert any(file["file"] == "top.sv" for file in syntax["files"])
    limited_syntax = dump_syntax_tree_summary(bundle, max_files=1)
    assert len(limited_syntax["files"]) == 1
    assert limited_syntax["summary"]["file_count"] == 3
    assert limited_syntax["summary"]["truncation"]["truncated"] is True

    preprocessing = preprocess_files(bundle)
    assert preprocessing["project_status"]["status"] == "ok"
    assert preprocessing["mode"] == "summary_only"
    assert preprocessing["effective_defines"] == {"WIDTH": "8"}
    assert preprocessing["files"][0]["include_directives"] == []
    limited_preprocessing = preprocess_files(bundle, max_files=1, max_excerpt_lines=1)
    assert len(limited_preprocessing["files"]) == 1
    assert len(limited_preprocessing["files"][0]["source_excerpt"].splitlines()) <= 1
    assert limited_preprocessing["summary"]["file_count"] == 3

    summary = get_project_summary(bundle, max_diagnostics=10, max_design_units=20)
    assert summary["project_status"]["status"] == "ok"
    assert summary["summary"]["file_count"] == 3
    assert summary["limits"]["max_diagnostics"] == 10


def test_diagnostics_on_broken_fixture() -> None:
    project = load_project_from_files(
        project_root=FIXTURES / "broken",
        files=["broken.sv"],
    )
    bundle = build_analysis(project)

    diagnostics = get_diagnostics(bundle)
    assert diagnostics["project_status"]["status"] == "incomplete"
    assert diagnostics["project_status"]["unresolved_references"] == 1
    assert diagnostics["summary"]["total"] == 1
    assert diagnostics["diagnostics"][0]["severity"] == "error"
    assert "missing_symbol" in diagnostics["diagnostics"][0]["message"]

    hidden_diagnostics = get_diagnostics(bundle, max_items=0)
    assert hidden_diagnostics["summary"]["total"] == 1
    assert hidden_diagnostics["summary"]["truncation"]["returned"] == 0
    assert hidden_diagnostics["summary"]["truncation"]["truncated"] is True

    description = describe_design_unit(bundle, name="broken")
    assert description["project_status"]["status"] == "incomplete"

    hierarchy = get_hierarchy(bundle)
    assert hierarchy["project_status"]["status"] == "incomplete"


def test_format_diagnostic_message_preserves_escaped_braces() -> None:
    diagnostic_engine = SimpleNamespace(getMessage=lambda _code: "literal {{}} before {} after")
    bundle = SimpleNamespace(diagnostic_engine=diagnostic_engine)
    diagnostic = SimpleNamespace(code="TEST", args=["payload"])

    message = _format_diagnostic_message(cast(Any, bundle), cast(Any, diagnostic))

    assert message == "literal {} before payload after"
