#!/usr/bin/env python3
"""Run text-only versus pyslang-backed comparison evals."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from mcp.types import CallToolResult

from pyslang_mcp.cache import AnalysisCache
from pyslang_mcp.server import PUBLIC_TOOL_NAMES, create_server


MODULE_RE = re.compile(r"^\s*(?:module|interface|package)\s+([A-Za-z_][A-Za-z0-9_$]*)", re.M)
HDL_SUFFIXES = {".sv", ".svh", ".v", ".vh"}


def load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_source_files(root: Path, case_input: dict[str, Any]) -> list[Path]:
    files = case_input.get("files")
    if isinstance(files, list):
        return [root / rel for rel in files if isinstance(rel, str)]

    filelist = case_input.get("filelist")
    if isinstance(filelist, str):
        return _resolve_filelist(root=root, filelist=root / filelist, seen=set())

    return sorted(path for path in root.rglob("*") if path.suffix in HDL_SUFFIXES)


def _resolve_filelist(*, root: Path, filelist: Path, seen: set[Path]) -> list[Path]:
    filelist = filelist.resolve()
    if filelist in seen:
        return []
    seen.add(filelist)

    files: list[Path] = []
    for raw_line in filelist.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("//", 1)[0].strip()
        if not line:
            continue
        tokens = line.split()
        index = 0
        while index < len(tokens):
            token = tokens[index]
            if token in {"-f", "-F"} and index + 1 < len(tokens):
                nested = (filelist.parent / tokens[index + 1]).resolve()
                files.extend(_resolve_filelist(root=root, filelist=nested, seen=seen))
                index += 2
                continue
            if token.startswith(("-f", "-F")) and len(token) > 2:
                nested = (filelist.parent / token[2:]).resolve()
                files.extend(_resolve_filelist(root=root, filelist=nested, seen=seen))
            elif token.startswith("+incdir+") or token.startswith("-I") or token.startswith("-D"):
                pass
            elif Path(token).suffix in HDL_SUFFIXES:
                files.append((filelist.parent / token).resolve())
            index += 1

    return [path for path in files if root.resolve() in path.parents or path == root.resolve()]


def run_baseline(case: dict[str, Any], evals_dir: Path) -> dict[str, Any]:
    root = evals_dir / case["fixture_root"]
    case_input = cast(dict[str, Any], case.get("input", {}))
    files = resolve_source_files(root, case_input)

    text = ""
    readable_files = []
    for path in files:
        if path.is_file():
            readable_files.append(path)
            text += path.read_text(encoding="utf-8", errors="replace") + "\n"

    query = case_input.get("query")
    query_hits = text.count(query) if isinstance(query, str) else None
    expected_tool_count = len(case.get("expected_tool_evidence", []))
    return {
        "mode": "without_skill_text_only",
        "source_file_count": len(readable_files),
        "line_count": text.count("\n"),
        "regex_design_units": sorted(set(MODULE_RE.findall(text))),
        "query": query,
        "query_text_hits": query_hits,
        "expected_compiler_evidence_count": expected_tool_count,
        "compiler_evidence_count": 0,
        "compiler_evidence_rate": 0.0,
        "capabilities": ["text_read", "regex_design_unit_scan", "literal_query_count"],
        "missing_capabilities": [
            "compiler_diagnostics",
            "elaborated_hierarchy",
            "semantic_symbol_references",
            "preprocessor_context",
        ],
    }


async def call_tool(server: Any, tool_name: str, arguments: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    result = await server.call_tool(tool_name, arguments)
    assert isinstance(result, CallToolResult)
    assert result.structuredContent is not None
    structured = cast(dict[str, Any], result.structuredContent)
    payload = structured.get("result", structured)
    return cast(dict[str, Any], payload), bool(result.isError)


def project_args(case: dict[str, Any], evals_dir: Path) -> dict[str, Any]:
    root = evals_dir / case["fixture_root"]
    case_input = cast(dict[str, Any], case.get("input", {}))
    args: dict[str, Any] = {"project_root": str(root)}
    if "filelist" in case_input:
        args["filelist"] = case_input["filelist"]
    else:
        args["files"] = case_input.get("files", [])
    if case_input.get("top_modules"):
        args["top_modules"] = case_input["top_modules"]
    if case_input.get("include_dirs"):
        args["include_dirs"] = case_input["include_dirs"]
    if case_input.get("defines"):
        args["defines"] = case_input["defines"]
    return args


def summarize_tool_payload(tool_name: str, payload: dict[str, Any], is_error: bool) -> dict[str, Any]:
    if is_error:
        error = payload.get("error", {})
        return {
            "ok": False,
            "error_code": error.get("code"),
            "error_message": error.get("message"),
        }

    if tool_name in {"pyslang_parse_files", "pyslang_parse_filelist"}:
        parse = payload.get("parse", {})
        return {
            "ok": True,
            "status": payload.get("project_status", {}).get("status"),
            "file_count": parse.get("file_count"),
            "diagnostic_count": parse.get("diagnostic_count"),
        }
    if tool_name == "pyslang_get_diagnostics":
        summary = payload.get("summary", {})
        return {
            "ok": True,
            "status": payload.get("project_status", {}).get("status"),
            "diagnostic_total": summary.get("total"),
            "severity_counts": summary.get("severity_counts", {}),
        }
    if tool_name == "pyslang_list_design_units":
        summary = payload.get("summary", {})
        return {
            "ok": True,
            "design_unit_total": summary.get("total"),
            "by_kind": summary.get("by_kind", {}),
        }
    if tool_name == "pyslang_describe_design_unit":
        unit = payload.get("design_unit") or {}
        return {
            "ok": True,
            "found": payload.get("found"),
            "name": unit.get("name"),
            "port_count": len(unit.get("ports", [])),
            "child_instance_count": len(unit.get("child_instances", [])),
        }
    if tool_name == "pyslang_get_hierarchy":
        summary = payload.get("summary", {})
        return {
            "ok": True,
            "top_instances": summary.get("top_instances", []),
            "total_instances": summary.get("total_instances"),
        }
    if tool_name == "pyslang_find_symbol":
        summary = payload.get("summary", {})
        return {
            "ok": True,
            "query": payload.get("query"),
            "declaration_count": summary.get("declaration_count"),
            "reference_count": summary.get("reference_count"),
        }
    if tool_name == "pyslang_dump_syntax_tree_summary":
        summary = payload.get("summary", {})
        return {
            "ok": True,
            "file_count": summary.get("file_count"),
        }
    return {"ok": True}


async def run_skill_mode(case: dict[str, Any], evals_dir: Path) -> dict[str, Any]:
    server = create_server(cache=AnalysisCache())
    expected = cast(list[str], case.get("expected_tool_evidence", []))
    args = project_args(case, evals_dir)
    case_input = cast(dict[str, Any], case.get("input", {}))
    top_modules = [item for item in case_input.get("top_modules", []) if isinstance(item, str)]
    query = case_input.get("query")

    tool_runs: dict[str, Any] = {}

    for expected_tool in expected:
        if expected_tool == "pyslang_parse_files":
            payload, is_error = await call_tool(server, PUBLIC_TOOL_NAMES["parse_files"], args)
            tool_runs[expected_tool] = summarize_tool_payload(expected_tool, payload, is_error)
        elif expected_tool == "pyslang_parse_filelist":
            payload, is_error = await call_tool(server, PUBLIC_TOOL_NAMES["parse_filelist"], args)
            tool_runs[expected_tool] = summarize_tool_payload(expected_tool, payload, is_error)
        elif expected_tool == "pyslang_get_diagnostics":
            payload, is_error = await call_tool(server, PUBLIC_TOOL_NAMES["get_diagnostics"], args)
            tool_runs[expected_tool] = summarize_tool_payload(expected_tool, payload, is_error)
        elif expected_tool == "pyslang_list_design_units":
            payload, is_error = await call_tool(server, PUBLIC_TOOL_NAMES["list_design_units"], args)
            tool_runs[expected_tool] = summarize_tool_payload(expected_tool, payload, is_error)
        elif expected_tool == "pyslang_describe_design_unit":
            summaries = []
            for top in top_modules:
                payload, is_error = await call_tool(
                    server,
                    PUBLIC_TOOL_NAMES["describe_design_unit"],
                    {**args, "name": top},
                )
                summaries.append(summarize_tool_payload(expected_tool, payload, is_error))
            tool_runs[expected_tool] = {"ok": all(item.get("ok") for item in summaries), "runs": summaries}
        elif expected_tool == "pyslang_get_hierarchy":
            payload, is_error = await call_tool(server, PUBLIC_TOOL_NAMES["get_hierarchy"], args)
            tool_runs[expected_tool] = summarize_tool_payload(expected_tool, payload, is_error)
        elif expected_tool == "pyslang_find_symbol":
            if isinstance(query, str):
                payload, is_error = await call_tool(
                    server,
                    PUBLIC_TOOL_NAMES["find_symbol"],
                    {**args, "query": query, "match_mode": "contains", "include_references": True},
                )
                tool_runs[expected_tool] = summarize_tool_payload(expected_tool, payload, is_error)
            else:
                tool_runs[expected_tool] = {"ok": False, "error_message": "case has no query"}
        elif expected_tool == "pyslang_dump_syntax_tree_summary":
            payload, is_error = await call_tool(
                server,
                PUBLIC_TOOL_NAMES["dump_syntax_tree_summary"],
                args,
            )
            tool_runs[expected_tool] = summarize_tool_payload(expected_tool, payload, is_error)

    successful = sum(1 for item in tool_runs.values() if item.get("ok"))
    return {
        "mode": "with_skill_pyslang_mcp",
        "expected_tool_count": len(expected),
        "successful_tool_count": successful,
        "tool_success_rate": successful / len(expected) if expected else 0.0,
        "tool_runs": tool_runs,
    }


def write_reports(report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "comparison.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# pyslang-verilog-context Comparison Eval",
        "",
        f"Generated: {report['generated_at']}",
        "",
        "| Case | Baseline files | Baseline units | Skill tools | Skill rate |",
        "|---|---:|---:|---:|---:|",
    ]
    for case in report["cases"]:
        baseline = case["without_skill"]
        skill = case["with_skill"]
        lines.append(
            "| {id} | {files} | {units} | {tools} | {rate:.2f} |".format(
                id=case["id"],
                files=baseline["source_file_count"],
                units=len(baseline["regex_design_units"]),
                tools=(
                    f"{skill['successful_tool_count']}/"
                    f"{skill['expected_tool_count']}"
                ),
                rate=skill["tool_success_rate"],
            )
        )
    lines.append("")
    total_success = sum(case["with_skill"]["successful_tool_count"] for case in report["cases"])
    total_expected = sum(case["with_skill"]["expected_tool_count"] for case in report["cases"])
    lines.append(f"Skill evidence coverage: {total_success}/{total_expected} expected tool calls.")
    lines.append(
        "Baseline is text-only regex/filelist evidence with 0 compiler-backed "
        "tool calls. Skill mode uses the expected `pyslang-mcp` calls from the "
        "manifest."
    )
    (output_dir / "comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


async def run(args: argparse.Namespace) -> int:
    manifest_path = args.manifest
    manifest = load_manifest(manifest_path)
    evals_dir = manifest_path.parent
    selected = set(args.case or [])
    cases = [
        case
        for case in manifest.get("cases", [])
        if not selected or case.get("id") in selected
    ]

    report_cases = []
    for case in cases:
        baseline = run_baseline(case, evals_dir)
        skill = await run_skill_mode(case, evals_dir)
        report_cases.append(
            {
                "id": case["id"],
                "prompt": case["prompt"],
                "fixture_root": case["fixture_root"],
                "without_skill": baseline,
                "with_skill": skill,
            }
        )

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "manifest": str(manifest_path),
        "case_count": len(report_cases),
        "cases": report_cases,
    }
    write_reports(report, args.output_dir)
    print(f"wrote {len(report_cases)} comparison cases to {args.output_dir}")
    return 0


def main() -> int:
    skill_dir = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        type=Path,
        default=skill_dir / "evals" / "manifest.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=skill_dir / "evals" / "reports",
    )
    parser.add_argument("--case", action="append", help="Run one case id; repeatable.")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
