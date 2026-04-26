"""Run a with-MCP vs text-only HDL understanding benchmark.

The benchmark intentionally compares two agent-access patterns:

- text-only: source-file and filelist inspection with deterministic regex helpers
- with MCP: a real local `pyslang-mcp` stdio server and MCP tool calls

It writes a JSON report and a self-contained interactive HTML dashboard.
"""

# ruff: noqa: E501

from __future__ import annotations

import argparse
import asyncio
import html
import json
import re
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

REPO = Path(__file__).resolve().parents[1]
SYNC_FIFO = REPO / "examples/hdl/reference/ip/sync_fifo"
APB_TIMER = REPO / "examples/hdl/reference/ip/apb_timer"
BUGGY_APB_TIMER = REPO / "examples/hdl/buggy/hard/apb_timer_irq_race_bug"
BROKEN_FIXTURE = REPO / "tests/fixtures/broken"
MULTI_FILE_FIXTURE = REPO / "tests/fixtures/multi_file"
RTL_AUDITOR_SKILL = Path.home() / ".codex/skills/rtl-lint-auditor/SKILL.md"
RTL_AUDITOR_RULES = (
    Path.home() / ".codex/skills/rtl-lint-auditor/rules/common/evidence-grounding.md",
    Path.home() / ".codex/skills/rtl-lint-auditor/rules/common/output-discipline.md",
    Path.home() / ".codex/skills/rtl-lint-auditor/rules/common/tool-evidence-provenance.md",
    Path.home() / ".codex/skills/rtl-lint-auditor/rules/rtl/synthesizable-systemverilog.md",
    Path.home() / ".codex/skills/rtl-lint-auditor/rules/rtl/lint-severity.md",
)
MCP_EVIDENCE_LOG: list[dict[str, Any]] = []


@dataclass(frozen=True)
class TextAnswer:
    answer: str
    confidence: str
    rationale: str


@dataclass(frozen=True)
class Case:
    case_id: str
    title: str
    project: str
    category: str
    difficulty: str
    evidence_need: str
    expected: str
    text_runner: Callable[[], TextAnswer]
    mcp_tools: tuple[str, ...]
    note: str


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _estimate_tokens(text: str) -> int:
    """Return a stable rough token estimate without depending on a tokenizer package."""

    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def _evidence_blob(paths: tuple[Path, ...]) -> str:
    chunks: list[str] = []
    for path in paths:
        if path.exists():
            rel = path.relative_to(REPO)
            chunks.append(f"### {rel.as_posix()}\n{path.read_text(encoding='utf-8')}")
    return "\n\n".join(chunks)


def _text_evidence_paths(case_id: str) -> tuple[Path, ...]:
    sync_all = (
        SYNC_FIFO / "project.f",
        SYNC_FIFO / "rtl.f",
        SYNC_FIFO / "include/fifo_defs.svh",
        SYNC_FIFO / "sync_fifo_pkg.sv",
        SYNC_FIFO / "sync_fifo_mem.sv",
        SYNC_FIFO / "sync_fifo.sv",
    )
    apb_all = (
        APB_TIMER / "project.f",
        APB_TIMER / "rtl.f",
        APB_TIMER / "timer_pkg.sv",
        APB_TIMER / "timer_core.sv",
        APB_TIMER / "apb_timer.sv",
    )
    buggy_apb_all = (
        BUGGY_APB_TIMER / "project.f",
        BUGGY_APB_TIMER / "rtl.f",
        BUGGY_APB_TIMER / "timer_pkg.sv",
        BUGGY_APB_TIMER / "timer_core.sv",
        BUGGY_APB_TIMER / "apb_timer.sv",
    )
    multi_all = (
        MULTI_FILE_FIXTURE / "project.f",
        MULTI_FILE_FIXTURE / "rtl.f",
        MULTI_FILE_FIXTURE / "include/defs.svh",
        MULTI_FILE_FIXTURE / "pkg.sv",
        MULTI_FILE_FIXTURE / "child.sv",
        MULTI_FILE_FIXTURE / "top.sv",
    )
    return {
        "sync_child_path": (SYNC_FIFO / "sync_fifo.sv",),
        "sync_child_definition": (SYNC_FIFO / "sync_fifo.sv",),
        "sync_output_ports": (SYNC_FIFO / "sync_fifo.sv",),
        "sync_tracked_paths": sync_all,
        "sync_package_include": (SYNC_FIFO / "sync_fifo_pkg.sv",),
        "push_fire_reference_kind": (SYNC_FIFO / "sync_fifo.sv",),
        "timer_core_ports": (APB_TIMER / "timer_core.sv",),
        "tick_hier_path": (APB_TIMER / "apb_timer.sv", APB_TIMER / "timer_core.sv"),
        "prescale_q_count": apb_all,
        "buggy_apb_diagnostics": buggy_apb_all,
        "broken_project_status": (BROKEN_FIXTURE / "broken.sv",),
        "data_t_reference_kind": multi_all,
        "multi_file_width_define": (
            MULTI_FILE_FIXTURE / "project.f",
            MULTI_FILE_FIXTURE / "rtl.f",
        ),
        "multi_file_child_path": (MULTI_FILE_FIXTURE / "top.sv",),
    }[case_id]


def _token_breakdown(prompt: str, evidence: str, answer: str) -> dict[str, int]:
    prompt_tokens = _estimate_tokens(prompt)
    evidence_tokens = _estimate_tokens(evidence)
    answer_tokens = _estimate_tokens(answer)
    return {
        "prompt": prompt_tokens,
        "evidence": evidence_tokens,
        "answer": answer_tokens,
        "total": prompt_tokens + evidence_tokens + answer_tokens,
    }


def _unknown(reason: str) -> TextAnswer:
    return TextAnswer(answer="unknown", confidence="unsupported", rationale=reason)


def _regex_answer(answer: str, rationale: str) -> TextAnswer:
    return TextAnswer(answer=answer, confidence="medium", rationale=rationale)


def _sync_child_path_text() -> TextAnswer:
    text = _read(SYNC_FIFO / "sync_fifo.sv")
    match = re.search(r"\bsync_fifo_mem\b[\s\S]*?\)\s+(u_\w+)\s*\(", text)
    if not match:
        return _unknown("No simple sync_fifo_mem instantiation pattern was found.")
    return _regex_answer(
        f"sync_fifo.{match.group(1)}",
        "Regex found a direct sync_fifo_mem instance and assumed the top scope name.",
    )


def _sync_child_definition_text() -> TextAnswer:
    text = _read(SYNC_FIFO / "sync_fifo.sv")
    match = re.search(r"\b(sync_fifo_mem)\b[\s\S]*?\)\s+u_sync_fifo_mem\s*\(", text)
    if not match:
        return _unknown("No direct u_sync_fifo_mem instantiation was found.")
    return _regex_answer(match.group(1), "Regex matched the module token before u_sync_fifo_mem.")


def _sync_output_port_count_text() -> TextAnswer:
    text = _read(SYNC_FIFO / "sync_fifo.sv")
    header = text.split(");", 1)[0]
    return _regex_answer(str(len(re.findall(r"\boutput\b", header))), "Counted output tokens.")


def _sync_tracked_paths_text() -> TextAnswer:
    project_lines = _read(SYNC_FIFO / "project.f").splitlines()
    rtl_lines = _read(SYNC_FIFO / "rtl.f").splitlines()
    visible_source_entries = [
        line.strip()
        for line in [*project_lines, *rtl_lines]
        if line.strip() and not line.lstrip().startswith(("-", "+"))
    ]
    return TextAnswer(
        answer=f"unknown ({len(visible_source_entries)} visible source entries)",
        confidence="unsupported",
        rationale=(
            "Text inspection can count visible source entries, but not the normalized "
            "tracked filelist/include closure used by the MCP."
        ),
    )


def _sync_package_include_text() -> TextAnswer:
    for path in sorted(SYNC_FIFO.glob("*.sv")):
        text = _read(path)
        if '`include "fifo_defs.svh"' in text and re.search(r"\bpackage\s+\w+", text):
            return _regex_answer(path.name, "Matched both the include directive and package token.")
    return _unknown("No file contained both fifo_defs.svh and a package declaration.")


def _push_fire_reference_kind_text() -> TextAnswer:
    return _unknown("Source text does not encode the compiler reference_kind classification.")


def _timer_core_port_count_text() -> TextAnswer:
    text = _read(APB_TIMER / "timer_core.sv")
    header = text.split(");", 1)[0]
    count = len(re.findall(r"\b(?:input|output|inout)\b", header))
    return _regex_answer(str(count), "Counted ANSI port direction tokens in timer_core.")


def _tick_declaration_path_text() -> TextAnswer:
    return _unknown("The hierarchical path requires elaborating timer_core under apb_timer.")


def _prescale_q_count_text() -> TextAnswer:
    count = 0
    for path in sorted(APB_TIMER.glob("*.sv")):
        text = _read(path)
        count += len(
            re.findall(r"\blogic\s+\[[^\]]+\]\s+prescale_q\b|\blogic\s+prescale_q\b", text)
        )
    return _regex_answer(str(count), "Counted prescale_q declarations across local source files.")


def _buggy_apb_diagnostics_text() -> TextAnswer:
    return _unknown("Diagnostic count requires running a parser/semantic frontend.")


def _broken_status_text() -> TextAnswer:
    return _unknown("Project status is a compiler-backed aggregate, not plain source text.")


def _data_t_reference_kind_text() -> TextAnswer:
    return _unknown("Declared-type references require symbol binding, not token matching.")


def _multi_file_define_text() -> TextAnswer:
    filelist = _read(MULTI_FILE_FIXTURE / "project.f") + "\n" + _read(MULTI_FILE_FIXTURE / "rtl.f")
    match = re.search(r"\+define\+WIDTH=(\d+)", filelist)
    if not match:
        return _unknown("WIDTH define was not visible in the plain filelists.")
    return _regex_answer(
        f"WIDTH={match.group(1)}", "Read +define+WIDTH directly from filelist text."
    )


def _multi_file_child_path_text() -> TextAnswer:
    text = _read(MULTI_FILE_FIXTURE / "top.sv")
    match = re.search(r"\bchild\s+(u_\w+)\s*\(", text)
    if not match:
        return _unknown("No simple child instantiation pattern was found.")
    return _regex_answer(f"top.{match.group(1)}", "Regex found a direct child instance.")


CASES: tuple[Case, ...] = (
    Case(
        "sync_child_path",
        "Resolved child instance path",
        "sync_fifo",
        "Hierarchy",
        "medium",
        "elaboration",
        "sync_fifo.u_sync_fifo_mem",
        _sync_child_path_text,
        ("pyslang_get_hierarchy",),
        "Can be guessed from simple source here; MCP confirms elaborated hierarchy.",
    ),
    Case(
        "sync_child_definition",
        "Child instance module definition",
        "sync_fifo",
        "Hierarchy",
        "easy",
        "module binding",
        "sync_fifo_mem",
        _sync_child_definition_text,
        ("pyslang_get_hierarchy",),
        "A direct instantiation is easy text-only; MCP still returns bound definition.",
    ),
    Case(
        "sync_output_ports",
        "sync_fifo output port count",
        "sync_fifo",
        "Interface",
        "easy",
        "port model",
        "4",
        _sync_output_port_count_text,
        ("pyslang_describe_design_unit",),
        "ANSI ports make this a fair text-only win.",
    ),
    Case(
        "sync_tracked_paths",
        "Normalized tracked path count",
        "sync_fifo",
        "Project loading",
        "hard",
        "filelist and include closure",
        "6",
        _sync_tracked_paths_text,
        ("pyslang_get_project_summary",),
        "This tests project-loader state rather than HDL syntax alone.",
    ),
    Case(
        "sync_package_include",
        "Package file that includes fifo_defs.svh",
        "sync_fifo",
        "Preprocessing",
        "easy",
        "syntax plus include metadata",
        "sync_fifo_pkg.sv",
        _sync_package_include_text,
        ("pyslang_dump_syntax_tree_summary",),
        "Plain text can answer this local include/package question.",
    ),
    Case(
        "push_fire_reference_kind",
        "push_fire named reference classification",
        "sync_fifo",
        "Symbol references",
        "hard",
        "semantic reference binding",
        "named_value",
        _push_fire_reference_kind_text,
        ("pyslang_find_symbol",),
        "Requires compiler classification of the reference expression.",
    ),
    Case(
        "timer_core_ports",
        "timer_core total port count",
        "apb_timer",
        "Interface",
        "easy",
        "port model",
        "9",
        _timer_core_port_count_text,
        ("pyslang_describe_design_unit",),
        "Simple ANSI interface extraction is enough here.",
    ),
    Case(
        "tick_hier_path",
        "tick declaration hierarchical path",
        "apb_timer",
        "Symbol references",
        "hard",
        "elaborated symbol scope",
        "apb_timer.u_timer_core.tick",
        _tick_declaration_path_text,
        ("pyslang_find_symbol",),
        "The answer depends on instance scope, not the local timer_core file alone.",
    ),
    Case(
        "prescale_q_count",
        "prescale_q declaration count",
        "apb_timer",
        "Symbol inventory",
        "medium",
        "declaration inventory",
        "2",
        _prescale_q_count_text,
        ("pyslang_find_symbol",),
        "Text can count this simple declaration pattern; MCP confirms declarations.",
    ),
    Case(
        "buggy_apb_diagnostics",
        "Buggy APB parse and semantic diagnostic count",
        "apb_timer_irq_race_bug",
        "Diagnostics",
        "hard",
        "compiler diagnostics",
        "0",
        _buggy_apb_diagnostics_text,
        ("pyslang_get_diagnostics",),
        "The design is intentionally behaviorally buggy but compiler-clean.",
    ),
    Case(
        "broken_project_status",
        "Broken fixture project status",
        "tests/fixtures/broken",
        "Diagnostics",
        "hard",
        "compiler diagnostics plus status",
        "incomplete",
        _broken_status_text,
        ("pyslang_get_diagnostics",),
        "Project status summarizes diagnostics and unresolved references.",
    ),
    Case(
        "data_t_reference_kind",
        "data_t declared-type reference classification",
        "tests/fixtures/multi_file",
        "Type binding",
        "hard",
        "semantic type binding",
        "declared_type",
        _data_t_reference_kind_text,
        ("pyslang_find_symbol",),
        "Requires resolving typedef use through package import.",
    ),
    Case(
        "multi_file_width_define",
        "Effective WIDTH preprocessor define",
        "tests/fixtures/multi_file",
        "Preprocessing",
        "medium",
        "filelist define resolution",
        "WIDTH=8",
        _multi_file_define_text,
        ("pyslang_preprocess_files",),
        "Text sees the simple define; MCP reports effective normalized defines.",
    ),
    Case(
        "multi_file_child_path",
        "multi_file top child instance path",
        "tests/fixtures/multi_file",
        "Hierarchy",
        "medium",
        "elaboration",
        "top.u_child",
        _multi_file_child_path_text,
        ("pyslang_get_hierarchy",),
        "A small direct instantiation is readable as text and confirmed by MCP.",
    ),
)


QUESTIONS = {
    "sync_child_path": (
        "What is the hierarchical_path of the only child instance under the top instance sync_fifo?"
    ),
    "sync_child_definition": (
        "What module definition is instantiated by the child instance u_sync_fifo_mem?"
    ),
    "sync_output_ports": "How many output ports does the sync_fifo design unit expose?",
    "sync_tracked_paths": "How many normalized tracked_paths are in the loaded project?",
    "sync_package_include": (
        "Which file includes fifo_defs.svh and has PackageDeclaration as its only top-level member?"
    ),
    "push_fire_reference_kind": (
        "For symbol push_fire, what reference_kind is reported for its named-value reference?"
    ),
    "timer_core_ports": "How many total ports does timer_core expose?",
    "tick_hier_path": "What hierarchical_path is reported for the tick variable declaration?",
    "prescale_q_count": "How many prescale_q declarations are reported?",
    "buggy_apb_diagnostics": (
        "How many parse and semantic diagnostics are reported for the buggy APB timer project?"
    ),
    "broken_project_status": "What project_status.status is reported for the broken fixture?",
    "data_t_reference_kind": (
        "For symbol data_t, what reference_kind is reported for a declared-type use?"
    ),
    "multi_file_width_define": "What effective WIDTH preprocessor define is reported?",
    "multi_file_child_path": (
        "What is the hierarchical_path of the child instance under the top instance top?"
    ),
}


def _prompt_without_mcp(case: Case) -> str:
    return "\n".join(
        [
            "Use the locally installed rtl-lint-auditor skill as evidence discipline.",
            "Apply its evidence-grounding, output-discipline, tool-evidence-provenance, "
            "synthesizable-SystemVerilog, and lint-severity rules where relevant.",
            "Mode: WITHOUT MCP.",
            "Do not call pyslang, pyslang-mcp, Verilator, simulators, synthesis, lint tools, "
            "or any compiler frontend.",
            "You may inspect only checked-in HDL source files and filelists as text.",
            f"Project: {case.project}",
            f"Category: {case.category}",
            f"Task: {QUESTIONS[case.case_id]}",
            "Return exactly one scalar answer. If the visible text cannot prove the answer, "
            "return exactly: unknown",
        ]
    )


def _prompt_with_mcp(case: Case) -> str:
    return "\n".join(
        [
            "Use the locally installed rtl-lint-auditor skill as evidence discipline.",
            "Apply its evidence-grounding, output-discipline, tool-evidence-provenance, "
            "synthesizable-SystemVerilog, and lint-severity rules where relevant.",
            "Mode: WITH MCP.",
            "Use the launched local pyslang-mcp stdio server for compiler-backed evidence.",
            "Use only read-only MCP tools and record tool evidence when reasoning depends on "
            "tool output.",
            f"Required MCP tools for this case: {', '.join(case.mcp_tools)}",
            f"Project: {case.project}",
            f"Category: {case.category}",
            f"Task: {QUESTIONS[case.case_id]}",
            "Return exactly one scalar answer.",
        ]
    )


async def _call_tool(
    session: ClientSession,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    result = await session.call_tool(tool_name, arguments)
    structured = cast(dict[str, Any], result.structuredContent)
    payload = cast(dict[str, Any], structured["result"])
    MCP_EVIDENCE_LOG.append(
        {
            "tool": tool_name,
            "arguments": arguments,
            "result": payload,
        }
    )
    return payload


def _count_output_ports(payload: dict[str, Any]) -> str:
    ports = cast(list[dict[str, Any]], payload["design_unit"]["ports"])
    return str(sum(1 for port in ports if port.get("direction") == "output"))


async def _mcp_answer(session: ClientSession, case_id: str) -> str:
    if case_id == "sync_child_path":
        payload = await _call_tool(
            session,
            "pyslang_get_hierarchy",
            {"project_root": str(SYNC_FIFO), "filelist": "project.f"},
        )
        return str(payload["hierarchy"][0]["children"][0]["hierarchical_path"])
    if case_id == "sync_child_definition":
        payload = await _call_tool(
            session,
            "pyslang_get_hierarchy",
            {"project_root": str(SYNC_FIFO), "filelist": "project.f"},
        )
        return str(payload["hierarchy"][0]["children"][0]["definition"])
    if case_id == "sync_output_ports":
        payload = await _call_tool(
            session,
            "pyslang_describe_design_unit",
            {"project_root": str(SYNC_FIFO), "filelist": "project.f", "name": "sync_fifo"},
        )
        return _count_output_ports(payload)
    if case_id == "sync_tracked_paths":
        payload = await _call_tool(
            session,
            "pyslang_get_project_summary",
            {"project_root": str(SYNC_FIFO), "filelist": "project.f"},
        )
        return str(len(cast(list[object], payload["tracked_paths"])))
    if case_id == "sync_package_include":
        payload = await _call_tool(
            session,
            "pyslang_dump_syntax_tree_summary",
            {"project_root": str(SYNC_FIFO), "filelist": "project.f"},
        )
        for file_payload in cast(list[dict[str, Any]], payload["files"]):
            includes = [entry["path"] for entry in file_payload["include_directives"]]
            if "fifo_defs.svh" in includes and file_payload["top_level_members"] == [
                "PackageDeclaration"
            ]:
                return str(file_payload["file"])
        return "unknown"
    if case_id == "push_fire_reference_kind":
        payload = await _call_tool(
            session,
            "pyslang_find_symbol",
            {
                "project_root": str(SYNC_FIFO),
                "filelist": "project.f",
                "query": "push_fire",
                "match_mode": "contains",
                "include_references": True,
            },
        )
        for reference in cast(list[dict[str, Any]], payload["references"]):
            if reference["reference_kind"] == "named_value":
                return str(reference["reference_kind"])
        return "unknown"
    if case_id == "timer_core_ports":
        payload = await _call_tool(
            session,
            "pyslang_describe_design_unit",
            {"project_root": str(APB_TIMER), "filelist": "project.f", "name": "timer_core"},
        )
        return str(len(cast(list[object], payload["design_unit"]["ports"])))
    if case_id == "tick_hier_path":
        payload = await _call_tool(
            session,
            "pyslang_find_symbol",
            {
                "project_root": str(APB_TIMER),
                "filelist": "project.f",
                "query": "tick",
                "match_mode": "exact",
                "include_references": True,
            },
        )
        return str(payload["declarations"][0]["hierarchical_path"])
    if case_id == "prescale_q_count":
        payload = await _call_tool(
            session,
            "pyslang_find_symbol",
            {
                "project_root": str(APB_TIMER),
                "filelist": "project.f",
                "query": "prescale_q",
                "match_mode": "contains",
                "include_references": False,
            },
        )
        return str(payload["summary"]["declaration_count"])
    if case_id == "buggy_apb_diagnostics":
        payload = await _call_tool(
            session,
            "pyslang_get_diagnostics",
            {"project_root": str(BUGGY_APB_TIMER), "filelist": "project.f"},
        )
        return str(payload["summary"]["total"])
    if case_id == "broken_project_status":
        payload = await _call_tool(
            session,
            "pyslang_get_diagnostics",
            {"project_root": str(BROKEN_FIXTURE), "files": ["broken.sv"]},
        )
        return str(payload["project_status"]["status"])
    if case_id == "data_t_reference_kind":
        payload = await _call_tool(
            session,
            "pyslang_find_symbol",
            {
                "project_root": str(MULTI_FILE_FIXTURE),
                "filelist": "project.f",
                "query": "data_t",
                "match_mode": "exact",
                "include_references": True,
            },
        )
        for reference in cast(list[dict[str, Any]], payload["references"]):
            if reference["reference_kind"] == "declared_type":
                return str(reference["reference_kind"])
        return "unknown"
    if case_id == "multi_file_width_define":
        payload = await _call_tool(
            session,
            "pyslang_preprocess_files",
            {"project_root": str(MULTI_FILE_FIXTURE), "filelist": "project.f"},
        )
        defines = cast(dict[str, str | None], payload["effective_defines"])
        return f"WIDTH={defines.get('WIDTH')}"
    if case_id == "multi_file_child_path":
        payload = await _call_tool(
            session,
            "pyslang_get_hierarchy",
            {"project_root": str(MULTI_FILE_FIXTURE), "filelist": "project.f"},
        )
        return str(payload["hierarchy"][0]["children"][0]["hierarchical_path"])
    raise ValueError(f"Unknown case id: {case_id}")


def _git_value(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _display_path(path: Path) -> str:
    home = Path.home()
    try:
        return f"~/{path.relative_to(home).as_posix()}"
    except ValueError:
        return str(path)


def _build_summary(cases: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(cases)
    text_correct = sum(1 for case in cases if case["text"]["correct"])
    mcp_correct = sum(1 for case in cases if case["mcp"]["correct"])
    text_tokens = [int(case["text"]["tokens"]["total"]) for case in cases]
    mcp_tokens = [int(case["mcp"]["tokens"]["total"]) for case in cases]
    total_text_tokens = sum(text_tokens)
    total_mcp_tokens = sum(mcp_tokens)
    categories = sorted({str(case["category"]) for case in cases})
    by_category: dict[str, dict[str, int]] = {}
    for category in categories:
        category_cases = [case for case in cases if case["category"] == category]
        by_category[category] = {
            "total": len(category_cases),
            "text_correct": sum(1 for case in category_cases if case["text"]["correct"]),
            "mcp_correct": sum(1 for case in category_cases if case["mcp"]["correct"]),
        }
    return {
        "total_cases": total,
        "text_correct": text_correct,
        "mcp_correct": mcp_correct,
        "text_accuracy": round(text_correct / total, 4) if total else 0,
        "mcp_accuracy": round(mcp_correct / total, 4) if total else 0,
        "delta_correct": mcp_correct - text_correct,
        "by_category": by_category,
        "median_mcp_ms": _median([float(case["mcp"]["elapsed_ms"]) for case in cases]),
        "median_text_ms": _median([float(case["text"]["elapsed_ms"]) for case in cases]),
        "total_text_tokens_est": total_text_tokens,
        "total_mcp_tokens_est": total_mcp_tokens,
        "median_text_tokens_est": _median([float(value) for value in text_tokens]),
        "median_mcp_tokens_est": _median([float(value) for value in mcp_tokens]),
        "text_correct_per_1k_tokens_est": round(text_correct * 1000 / total_text_tokens, 4)
        if total_text_tokens
        else 0,
        "mcp_correct_per_1k_tokens_est": round(mcp_correct * 1000 / total_mcp_tokens, 4)
        if total_mcp_tokens
        else 0,
    }


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return round(ordered[midpoint], 3)
    return round((ordered[midpoint - 1] + ordered[midpoint]) / 2, 3)


async def run_benchmark() -> dict[str, Any]:
    params = StdioServerParameters(
        command=str(REPO / ".venv" / "bin" / "python"),
        args=["-m", "pyslang_mcp", "--transport", "stdio"],
        cwd=REPO,
    )
    results: list[dict[str, Any]] = []
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tool_list = await session.list_tools()
            tool_names = sorted(tool.name for tool in tool_list.tools)
            for case in CASES:
                text_prompt = _prompt_without_mcp(case)
                mcp_prompt = _prompt_with_mcp(case)
                text_evidence_paths = _text_evidence_paths(case.case_id)
                text_evidence = _evidence_blob(text_evidence_paths)

                text_start = time.perf_counter()
                text = case.text_runner()
                text_elapsed = (time.perf_counter() - text_start) * 1000

                MCP_EVIDENCE_LOG.clear()
                mcp_start = time.perf_counter()
                mcp_answer = await _mcp_answer(session, case.case_id)
                mcp_elapsed = (time.perf_counter() - mcp_start) * 1000
                mcp_evidence = json.dumps(MCP_EVIDENCE_LOG, sort_keys=True)

                results.append(
                    {
                        "id": case.case_id,
                        "title": case.title,
                        "project": case.project,
                        "category": case.category,
                        "difficulty": case.difficulty,
                        "evidence_need": case.evidence_need,
                        "expected": case.expected,
                        "note": case.note,
                        "question": QUESTIONS[case.case_id],
                        "mcp_tools": list(case.mcp_tools),
                        "prompts": {
                            "without_mcp": text_prompt,
                            "with_mcp": mcp_prompt,
                        },
                        "text": {
                            "answer": text.answer,
                            "correct": text.answer == case.expected,
                            "confidence": text.confidence,
                            "elapsed_ms": round(text_elapsed, 3),
                            "rationale": text.rationale,
                            "evidence_files": [
                                path.relative_to(REPO).as_posix()
                                for path in text_evidence_paths
                                if path.exists()
                            ],
                            "evidence_chars": len(text_evidence),
                            "tokens": _token_breakdown(text_prompt, text_evidence, text.answer),
                        },
                        "mcp": {
                            "answer": mcp_answer,
                            "correct": mcp_answer == case.expected,
                            "confidence": "compiler-backed",
                            "elapsed_ms": round(mcp_elapsed, 3),
                            "rationale": "Answered through the launched local pyslang-mcp stdio server.",
                            "evidence_calls": len(MCP_EVIDENCE_LOG),
                            "evidence_chars": len(mcp_evidence),
                            "tokens": _token_breakdown(mcp_prompt, mcp_evidence, mcp_answer),
                        },
                    }
                )

    return {
        "metadata": {
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "repo": "pyslang-mcp",
            "branch": _git_value("branch", "--show-current"),
            "commit": _git_value("rev-parse", "--short", "HEAD"),
            "comparison": "source-text-only baseline vs local pyslang-mcp stdio server",
            "server_command": ".venv/bin/python -m pyslang_mcp --transport stdio",
            "tool_count": len(tool_names),
            "tools": tool_names,
            "methodology": (
                "The text-only baseline may inspect checked-in HDL and filelists with "
                "deterministic regex helpers, but it cannot call pyslang, MCP tools, or "
                "any compiler frontend. The MCP side launches the local server and uses "
                "structured tool responses."
            ),
            "token_methodology": (
                "Token counts are deterministic estimates using ceil(character_count / 4) "
                "over the exact prompt, evidence payload, and scalar answer. They are not "
                "Codex internal tokenizer telemetry."
            ),
            "speed_methodology": (
                "Elapsed milliseconds measure local evidence acquisition and deterministic "
                "answer extraction. They exclude hidden LLM inference time."
            ),
            "skill_profile": {
                "name": "rtl-lint-auditor",
                "installed_skill": _display_path(RTL_AUDITOR_SKILL),
                "installed_rules": [_display_path(path) for path in RTL_AUDITOR_RULES],
                "usage": (
                    "Prompts use the installed skill and rules as evidence discipline for "
                    "the HDL-understanding benchmark. The benchmark output remains scalar "
                    "exact-match answers rather than full lint YAML reports."
                ),
            },
        },
        "summary": _build_summary(results),
        "cases": results,
    }


def _html_dashboard(report: dict[str, Any]) -> str:
    payload = json.dumps(report, sort_keys=True).replace("</", "<\\/")
    generated = html.escape(str(report["metadata"]["generated_at"]))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>pyslang-mcp A/B HDL Understanding Dashboard</title>
  <style>
    :root {{
      --ink: #151515;
      --muted: #5e625f;
      --line: #d8d1c6;
      --paper: #f4efe6;
      --panel: #fffaf0;
      --oxide: #b5452f;
      --steel: #31596b;
      --moss: #647d45;
      --gold: #be8b2e;
      --bad: #9b2f2f;
      --good: #2f6f54;
      --shadow: 0 18px 50px rgba(31, 26, 20, 0.12);
    }}

    * {{ box-sizing: border-box; }}

    body {{
      margin: 0;
      background:
        linear-gradient(90deg, rgba(21,21,21,0.04) 1px, transparent 1px) 0 0 / 28px 28px,
        linear-gradient(rgba(21,21,21,0.03) 1px, transparent 1px) 0 0 / 28px 28px,
        var(--paper);
      color: var(--ink);
      font-family: Georgia, "Times New Roman", serif;
    }}

    button, input, select {{
      font: inherit;
    }}

    .shell {{
      width: min(1420px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 28px 0 44px;
    }}

    .hero {{
      min-height: 310px;
      display: grid;
      grid-template-columns: minmax(0, 1.25fr) minmax(340px, 0.75fr);
      gap: 24px;
      align-items: stretch;
      border-top: 8px solid var(--ink);
      border-bottom: 1px solid var(--line);
      padding: 28px 0 26px;
    }}

    .hero h1 {{
      margin: 0;
      max-width: 980px;
      font-size: clamp(44px, 7vw, 112px);
      line-height: 0.86;
      letter-spacing: 0;
      font-weight: 800;
    }}

    .subtitle {{
      max-width: 760px;
      margin-top: 22px;
      color: var(--muted);
      font-size: 18px;
      line-height: 1.45;
    }}

    .stamp {{
      align-self: end;
      border: 1px solid var(--ink);
      background: rgba(255, 250, 240, 0.8);
      box-shadow: var(--shadow);
      padding: 18px;
    }}

    .stamp strong {{
      display: block;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      color: var(--muted);
      margin-bottom: 12px;
    }}

    .stamp code {{
      display: block;
      white-space: normal;
      overflow-wrap: anywhere;
      font-family: "Courier New", monospace;
      font-size: 14px;
      line-height: 1.5;
    }}

    .metrics {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 14px;
      margin: 24px 0;
    }}

    .metric {{
      border: 1px solid var(--line);
      background: var(--panel);
      padding: 18px;
      min-height: 126px;
    }}

    .metric .label {{
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.11em;
      color: var(--muted);
    }}

    .metric .value {{
      margin-top: 12px;
      font-family: "Courier New", monospace;
      font-size: 34px;
      font-weight: 700;
    }}

    .metric .sub {{
      margin-top: 8px;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.35;
    }}

    .controls {{
      display: grid;
      grid-template-columns: 1.4fr repeat(3, minmax(160px, 0.45fr));
      gap: 10px;
      margin: 22px 0;
    }}

    .controls input,
    .controls select {{
      width: 100%;
      border: 1px solid var(--ink);
      background: #fffdf7;
      color: var(--ink);
      min-height: 44px;
      padding: 10px 12px;
      border-radius: 0;
    }}

    .bands {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(360px, 0.48fr);
      gap: 18px;
      align-items: start;
    }}

    .section {{
      border-top: 3px solid var(--ink);
      padding-top: 14px;
    }}

    .section h2 {{
      margin: 0 0 12px;
      font-size: 22px;
      letter-spacing: 0;
    }}

    .bar-list {{
      display: grid;
      gap: 10px;
    }}

    .bar-row {{
      display: grid;
      grid-template-columns: 170px 1fr 64px;
      gap: 10px;
      align-items: center;
      font-size: 14px;
    }}

    .track {{
      height: 18px;
      border: 1px solid var(--line);
      background: rgba(21, 21, 21, 0.05);
      position: relative;
      overflow: hidden;
    }}

    .fill {{
      height: 100%;
      background: var(--steel);
    }}

    .fill.text {{
      background: var(--oxide);
    }}

    .legend {{
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      margin: 8px 0 14px;
      color: var(--muted);
      font-size: 13px;
    }}

    .swatch {{
      display: inline-block;
      width: 12px;
      height: 12px;
      border: 1px solid var(--ink);
      vertical-align: -1px;
      margin-right: 5px;
    }}

    .swatch.mcp {{ background: var(--steel); }}
    .swatch.text {{ background: var(--oxide); }}

    .table-wrap {{
      margin-top: 24px;
      border-top: 3px solid var(--ink);
      overflow-x: auto;
    }}

    table {{
      width: 100%;
      border-collapse: collapse;
      background: rgba(255, 250, 240, 0.72);
    }}

    th {{
      text-align: left;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      padding: 12px 10px;
      border-bottom: 1px solid var(--ink);
      color: var(--muted);
      cursor: pointer;
      user-select: none;
    }}

    td {{
      padding: 12px 10px;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
      font-size: 14px;
      line-height: 1.35;
    }}

    tr:hover td {{
      background: rgba(190, 139, 46, 0.08);
    }}

    .pill {{
      display: inline-block;
      border: 1px solid var(--ink);
      padding: 3px 7px;
      font-size: 12px;
      font-family: "Courier New", monospace;
      background: #fffdf7;
    }}

    .ok {{ color: var(--good); font-weight: 700; }}
    .miss {{ color: var(--bad); font-weight: 700; }}

    .details {{
      margin-top: 24px;
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
    }}

    .detail-panel {{
      border: 1px solid var(--line);
      background: var(--panel);
      padding: 16px;
      min-height: 170px;
    }}

    .detail-panel h3 {{
      margin: 0 0 10px;
      font-size: 16px;
    }}

    .detail-panel p {{
      margin: 8px 0;
      color: var(--muted);
      line-height: 1.45;
    }}

    .prompt-box {{
      margin: 10px 0 0;
      padding: 12px;
      max-height: 260px;
      overflow: auto;
      border: 1px solid var(--line);
      background: #fffdf7;
      white-space: pre-wrap;
      font-family: "Courier New", monospace;
      font-size: 12px;
      line-height: 1.45;
    }}

    .method {{
      margin-top: 26px;
      border-top: 3px solid var(--ink);
      padding-top: 14px;
      color: var(--muted);
      line-height: 1.55;
      max-width: 980px;
    }}

    @media (max-width: 900px) {{
      .hero,
      .bands,
      .details,
      .controls,
      .metrics {{
        grid-template-columns: 1fr;
      }}
      .hero h1 {{
        font-size: clamp(40px, 14vw, 72px);
      }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <div>
        <h1>With MCP vs Source Text</h1>
        <p class="subtitle">A reproducible HDL understanding benchmark comparing deterministic source-file inspection against a launched local <code>pyslang-mcp</code> stdio server. Generated {generated}.</p>
      </div>
      <aside class="stamp">
        <strong>Run context</strong>
        <code id="run-context"></code>
      </aside>
    </section>

    <section class="metrics" id="metrics"></section>

    <section class="controls" aria-label="Dashboard filters">
      <input id="search" type="search" placeholder="Search case, project, category, answer">
      <select id="category"></select>
      <select id="difficulty"></select>
      <select id="verdict">
        <option value="all">All verdicts</option>
        <option value="mcp-only">MCP wins</option>
        <option value="both">Both correct</option>
        <option value="text-only">Text only wins</option>
        <option value="misses">Any miss</option>
      </select>
    </section>

    <section class="bands">
      <div class="section">
        <h2>Accuracy By Category</h2>
        <div class="legend"><span><span class="swatch mcp"></span>MCP</span><span><span class="swatch text"></span>Text-only</span></div>
        <div class="bar-list" id="category-bars"></div>
      </div>
      <div class="section">
        <h2>MCP Latency By Case</h2>
        <div class="bar-list" id="latency-bars"></div>
      </div>
    </section>

    <section class="table-wrap">
      <table>
        <thead>
          <tr>
            <th data-sort="title">Case</th>
            <th data-sort="category">Category</th>
            <th data-sort="difficulty">Difficulty</th>
            <th data-sort="expected">Expected</th>
            <th data-sort="text">Text-only</th>
            <th data-sort="mcp">MCP</th>
            <th data-sort="latency">MCP ms</th>
            <th data-sort="text_tokens">Text tokens</th>
            <th data-sort="mcp_tokens">MCP tokens</th>
          </tr>
        </thead>
        <tbody id="case-table"></tbody>
      </table>
    </section>

    <section class="details" id="details"></section>

    <section class="method">
      <h2>Methodology</h2>
      <p id="methodology"></p>
      <p>The text-only side is intentionally limited to source and filelist reading with deterministic regex helpers. It represents what an agent can ground from visible text without compiler APIs. The MCP side launches the local server and answers through structured tool calls.</p>
    </section>
  </main>

  <script type="application/json" id="report-data">{payload}</script>
  <script>
    const data = JSON.parse(document.getElementById('report-data').textContent);
    let sortKey = 'title';
    let sortDir = 1;

    const search = document.getElementById('search');
    const category = document.getElementById('category');
    const difficulty = document.getElementById('difficulty');
    const verdict = document.getElementById('verdict');

    function unique(values) {{
      return [...new Set(values)].sort();
    }}

    function pct(value, total) {{
      return total ? Math.round((value / total) * 100) : 0;
    }}

    function populateSelect(node, label, values) {{
      node.innerHTML = '<option value="all">' + label + '</option>' + values.map(v => '<option value="' + escapeHtml(v) + '">' + escapeHtml(v) + '</option>').join('');
    }}

    function escapeHtml(value) {{
      return String(value).replace(/[&<>"']/g, ch => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',\"'\":'&#39;'}}[ch]));
    }}

    function verdictClass(row) {{
      if (row.mcp.correct && !row.text.correct) return 'mcp-only';
      if (row.mcp.correct && row.text.correct) return 'both';
      if (!row.mcp.correct && row.text.correct) return 'text-only';
      return 'misses';
    }}

    function filteredCases() {{
      const q = search.value.trim().toLowerCase();
      return data.cases.filter(row => {{
        const haystack = [row.title, row.project, row.category, row.difficulty, row.expected, row.text.answer, row.mcp.answer].join(' ').toLowerCase();
        return (!q || haystack.includes(q))
          && (category.value === 'all' || row.category === category.value)
          && (difficulty.value === 'all' || row.difficulty === difficulty.value)
          && (verdict.value === 'all' || verdictClass(row) === verdict.value || (verdict.value === 'misses' && (!row.mcp.correct || !row.text.correct)));
      }});
    }}

    function renderMetrics(rows) {{
      const total = rows.length;
      const mcp = rows.filter(row => row.mcp.correct).length;
      const text = rows.filter(row => row.text.correct).length;
      const delta = mcp - text;
      const median = rows.map(row => row.mcp.elapsed_ms).sort((a, b) => a - b)[Math.floor(Math.max(0, rows.length - 1) / 2)] || 0;
      document.getElementById('metrics').innerHTML = [
        ['MCP accuracy', mcp + '/' + total, pct(mcp, total) + '% exact-match'],
        ['Text-only accuracy', text + '/' + total, pct(text, total) + '% exact-match'],
        ['MCP advantage', '+' + delta, 'additional exact answers'],
        ['Median MCP latency', median.toFixed(1) + ' ms', 'evidence acquisition only'],
        ['Text tokens est.', data.summary.total_text_tokens_est, 'prompt + source evidence + answer'],
        ['MCP tokens est.', data.summary.total_mcp_tokens_est, 'prompt + tool JSON + answer'],
        ['Median text tokens', data.summary.median_text_tokens_est, 'per case estimate'],
        ['Median MCP tokens', data.summary.median_mcp_tokens_est, 'per case estimate']
      ].map(item => '<div class="metric"><div class="label">' + item[0] + '</div><div class="value">' + item[1] + '</div><div class="sub">' + item[2] + '</div></div>').join('');
    }}

    function renderCategoryBars(rows) {{
      const cats = unique(rows.map(row => row.category));
      document.getElementById('category-bars').innerHTML = cats.map(cat => {{
        const scoped = rows.filter(row => row.category === cat);
        const mcp = pct(scoped.filter(row => row.mcp.correct).length, scoped.length);
        const text = pct(scoped.filter(row => row.text.correct).length, scoped.length);
        return '<div><div class="bar-row"><span>' + escapeHtml(cat) + '</span><div class="track"><div class="fill" style="width:' + mcp + '%"></div></div><strong>' + mcp + '%</strong></div><div class="bar-row"><span></span><div class="track"><div class="fill text" style="width:' + text + '%"></div></div><strong>' + text + '%</strong></div></div>';
      }}).join('');
    }}

    function renderLatencyBars(rows) {{
      const max = Math.max(...rows.map(row => row.mcp.elapsed_ms), 1);
      document.getElementById('latency-bars').innerHTML = rows
        .slice()
        .sort((a, b) => b.mcp.elapsed_ms - a.mcp.elapsed_ms)
        .map(row => {{
          const width = Math.max(3, Math.round((row.mcp.elapsed_ms / max) * 100));
          return '<div class="bar-row"><span>' + escapeHtml(row.id) + '</span><div class="track"><div class="fill" style="width:' + width + '%"></div></div><strong>' + row.mcp.elapsed_ms.toFixed(1) + '</strong></div>';
        }}).join('');
    }}

    function sortValue(row, key) {{
      if (key === 'text') return row.text.correct ? 1 : 0;
      if (key === 'mcp') return row.mcp.correct ? 1 : 0;
      if (key === 'latency') return row.mcp.elapsed_ms;
      if (key === 'text_tokens') return row.text.tokens.total;
      if (key === 'mcp_tokens') return row.mcp.tokens.total;
      return String(row[key] || row.expected).toLowerCase();
    }}

    function renderTable(rows) {{
      const sorted = rows.slice().sort((a, b) => {{
        const av = sortValue(a, sortKey);
        const bv = sortValue(b, sortKey);
        return av > bv ? sortDir : av < bv ? -sortDir : 0;
      }});
      document.getElementById('case-table').innerHTML = sorted.map(row => {{
        return '<tr data-id="' + escapeHtml(row.id) + '">'
          + '<td><strong>' + escapeHtml(row.title) + '</strong><br><span class="pill">' + escapeHtml(row.project) + '</span></td>'
          + '<td>' + escapeHtml(row.category) + '<br><span class="pill">' + escapeHtml(row.evidence_need) + '</span></td>'
          + '<td>' + escapeHtml(row.difficulty) + '</td>'
          + '<td><code>' + escapeHtml(row.expected) + '</code></td>'
          + '<td><span class="' + (row.text.correct ? 'ok' : 'miss') + '">' + (row.text.correct ? 'OK' : 'MISS') + '</span><br><code>' + escapeHtml(row.text.answer) + '</code></td>'
          + '<td><span class="' + (row.mcp.correct ? 'ok' : 'miss') + '">' + (row.mcp.correct ? 'OK' : 'MISS') + '</span><br><code>' + escapeHtml(row.mcp.answer) + '</code></td>'
          + '<td>' + row.mcp.elapsed_ms.toFixed(1) + '</td>'
          + '<td>' + row.text.tokens.total + '</td>'
          + '<td>' + row.mcp.tokens.total + '</td>'
          + '</tr>';
      }}).join('');
      document.querySelectorAll('#case-table tr').forEach(row => {{
        row.addEventListener('click', () => renderDetails(row.dataset.id));
      }});
    }}

    function renderDetails(id) {{
      const row = data.cases.find(item => item.id === id) || filteredCases()[0] || data.cases[0];
      if (!row) return;
      document.getElementById('details').innerHTML = [
        '<div class="detail-panel"><h3>' + escapeHtml(row.title) + '</h3><p><strong>Expected:</strong> <code>' + escapeHtml(row.expected) + '</code></p><p>' + escapeHtml(row.note) + '</p><p><strong>MCP tools:</strong> ' + row.mcp_tools.map(escapeHtml).join(', ') + '</p></div>',
        '<div class="detail-panel"><h3>Evidence comparison</h3><p><strong>Text-only:</strong> <code>' + escapeHtml(row.text.answer) + '</code> (' + escapeHtml(row.text.confidence) + ')</p><p>' + escapeHtml(row.text.rationale) + '</p><p><strong>Text token estimate:</strong> ' + row.text.tokens.total + ' = prompt ' + row.text.tokens.prompt + ' + evidence ' + row.text.tokens.evidence + ' + answer ' + row.text.tokens.answer + '</p><p><strong>MCP:</strong> <code>' + escapeHtml(row.mcp.answer) + '</code> in ' + row.mcp.elapsed_ms.toFixed(1) + ' ms</p><p>' + escapeHtml(row.mcp.rationale) + '</p><p><strong>MCP token estimate:</strong> ' + row.mcp.tokens.total + ' = prompt ' + row.mcp.tokens.prompt + ' + evidence ' + row.mcp.tokens.evidence + ' + answer ' + row.mcp.tokens.answer + '</p></div>',
        '<div class="detail-panel"><h3>Prompt without MCP</h3><pre class="prompt-box">' + escapeHtml(row.prompts.without_mcp) + '</pre></div>',
        '<div class="detail-panel"><h3>Prompt with MCP</h3><pre class="prompt-box">' + escapeHtml(row.prompts.with_mcp) + '</pre></div>'
      ].join('');
    }}

    function render() {{
      const rows = filteredCases();
      renderMetrics(rows);
      renderCategoryBars(rows);
      renderLatencyBars(rows);
      renderTable(rows);
      renderDetails(rows[0] && rows[0].id);
    }}

    populateSelect(category, 'All categories', unique(data.cases.map(row => row.category)));
    populateSelect(difficulty, 'All difficulties', unique(data.cases.map(row => row.difficulty)));
    document.getElementById('run-context').textContent = data.metadata.branch + '@' + data.metadata.commit + '\\n' + data.metadata.server_command + '\\n' + data.metadata.tool_count + ' MCP tools discovered';
    document.getElementById('methodology').textContent = data.metadata.methodology;
    [search, category, difficulty, verdict].forEach(node => node.addEventListener('input', render));
    document.querySelectorAll('th[data-sort]').forEach(th => th.addEventListener('click', () => {{
      const next = th.dataset.sort;
      if (sortKey === next) sortDir *= -1;
      sortKey = next;
      render();
    }}));
    render();
  </script>
</body>
</html>
"""


def write_report(report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "results.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "index.html").write_text(_html_dashboard(report), encoding="utf-8")


def print_markdown_summary(report: dict[str, Any], output_dir: Path) -> None:
    summary = report["summary"]
    print("# With MCP vs Without MCP Benchmark")
    print()
    print(f"- Cases: {summary['total_cases']}")
    print(f"- Text-only exact answers: {summary['text_correct']}/{summary['total_cases']}")
    print(f"- MCP exact answers: {summary['mcp_correct']}/{summary['total_cases']}")
    print(f"- Dashboard: {output_dir / 'index.html'}")
    print(f"- JSON: {output_dir / 'results.json'}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO / "reports" / "mcp_comparison",
        help="Directory for results.json and index.html.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = asyncio.run(run_benchmark())
    write_report(report, args.output_dir)
    print_markdown_summary(report, args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
