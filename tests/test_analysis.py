from __future__ import annotations

from pathlib import Path

from pyslang_mcp.analysis import (
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
    assert description["ports"][0]["name"] == "clk"
    assert description["child_instances"][0]["name"] == "u_child"
    assert "payload" in description["declared_names"]

    hierarchy = get_hierarchy(bundle)
    assert hierarchy["hierarchy"][0]["name"] == "top"
    assert hierarchy["hierarchy"][0]["children"][0]["name"] == "u_child"

    symbol_hits = find_symbol(bundle, query="payload", include_references=True)
    assert symbol_hits["summary"]["declaration_count"] >= 1
    assert symbol_hits["summary"]["reference_count"] >= 1

    syntax = dump_syntax_tree_summary(bundle)
    assert len(syntax["files"]) == 3
    assert any(file["file"] == "top.sv" for file in syntax["files"])

    preprocessing = preprocess_files(bundle)
    assert preprocessing["mode"] == "summary_only"
    assert preprocessing["files"][0]["include_directives"] == []

    summary = get_project_summary(bundle)
    assert summary["summary"]["file_count"] == 3


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
