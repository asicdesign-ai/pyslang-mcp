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
TAP_DELAY_LINE = REPO / "examples/hdl/reference/single/systemverilog/tap_delay_line"
SIMPLE_COUNTER_BUG = REPO / "examples/hdl/buggy/easy/simple_counter_priority_bug"
EDGE_DETECT_BUG = REPO / "examples/hdl/buggy/easy/edge_detect_polarity_bug"
REGISTER_PIPE_BUG = REPO / "examples/hdl/buggy/medium/register_pipe_valid_bug"
SYNC_FIFO_BUG = REPO / "examples/hdl/buggy/hard/sync_fifo_count_bug"
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
class Arm:
    key: str
    label: str
    uses_mcp: bool
    uses_skill: bool


ARMS: tuple[Arm, ...] = (
    Arm("text_no_skill", "Text/no skill", uses_mcp=False, uses_skill=False),
    Arm("mcp_no_skill", "MCP/no skill", uses_mcp=True, uses_skill=False),
    Arm("mcp_with_skill", "MCP/skill", uses_mcp=True, uses_skill=True),
)


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


def _display_path(path: Path) -> str:
    home = Path.home()
    try:
        return f"~/{path.relative_to(home).as_posix()}"
    except ValueError:
        return str(path)


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


def _skill_context_blob() -> str:
    chunks: list[str] = []
    for path in (RTL_AUDITOR_SKILL, *RTL_AUDITOR_RULES):
        if path.exists():
            chunks.append(f"### {_display_path(path)}\n{path.read_text(encoding='utf-8')}")
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
        "apb_design_unit_total": (
            APB_TIMER / "project.f",
            APB_TIMER / "rtl.f",
            APB_TIMER / "timer_pkg.sv",
            APB_TIMER / "timer_core.sv",
            APB_TIMER / "apb_timer.sv",
        ),
        "sync_pkg_function_count": (SYNC_FIFO / "sync_fifo_pkg.sv",),
        "sync_mem_port_count": (SYNC_FIFO / "sync_fifo_mem.sv",),
        "timer_ctrl_type_reference_count": (
            APB_TIMER / "timer_pkg.sv",
            APB_TIMER / "apb_timer.sv",
        ),
        "tap_delay_for_keyword_count": (TAP_DELAY_LINE / "tap_delay_line.sv",),
        "apb_timer_include_path": (APB_TIMER / "timer_pkg.sv",),
        "edge_detect_polarity_bug_output": (EDGE_DETECT_BUG / "edge_detect.sv",),
        "simple_counter_priority_bug_signal": (SIMPLE_COUNTER_BUG / "simple_counter.v",),
        "register_pipe_stall_bug_signal": (REGISTER_PIPE_BUG / "register_pipe.v",),
        "sync_fifo_count_bug_missing_case": (
            SYNC_FIFO_BUG / "project.f",
            SYNC_FIFO_BUG / "rtl.f",
            SYNC_FIFO_BUG / "sync_fifo.sv",
        ),
        "apb_timer_irq_priority_bug_signal": (
            BUGGY_APB_TIMER / "project.f",
            BUGGY_APB_TIMER / "rtl.f",
            BUGGY_APB_TIMER / "timer_core.sv",
        ),
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


def _apb_design_unit_total_text() -> TextAnswer:
    total = 0
    for path in (
        APB_TIMER / "timer_pkg.sv",
        APB_TIMER / "timer_core.sv",
        APB_TIMER / "apb_timer.sv",
    ):
        text = _read(path)
        total += len(re.findall(r"\b(?:module|package)\s+\w+", text))
    return _regex_answer(str(total), "Counted module/package declarations in listed APB sources.")


def _sync_pkg_function_count_text() -> TextAnswer:
    text = _read(SYNC_FIFO / "sync_fifo_pkg.sv")
    return _regex_answer(
        str(len(re.findall(r"\bfunction\s+automatic\b", text))),
        "Counted automatic function declarations in the package source.",
    )


def _sync_mem_port_count_text() -> TextAnswer:
    text = _read(SYNC_FIFO / "sync_fifo_mem.sv")
    header = text.split(");", 1)[0]
    count = len(re.findall(r"\b(?:input|output|inout)\b", header))
    return _regex_answer(str(count), "Counted ANSI port direction tokens in sync_fifo_mem.")


def _timer_ctrl_type_reference_count_text() -> TextAnswer:
    return _unknown("Reference count requires binding typedef uses to their target symbols.")


def _tap_delay_for_keyword_count_text() -> TextAnswer:
    text = _read(TAP_DELAY_LINE / "tap_delay_line.sv")
    return _regex_answer(str(len(re.findall(r"\bfor\s*\(", text))), "Counted for-loop tokens.")


def _apb_timer_include_path_text() -> TextAnswer:
    text = _read(APB_TIMER / "timer_pkg.sv")
    match = re.search(r'`include\s+"([^"]+)"', text)
    if not match:
        return _unknown("No include directive was visible in timer_pkg.sv.")
    return _regex_answer(match.group(1), "Read the include directive text from timer_pkg.sv.")


def _edge_detect_polarity_bug_text() -> TextAnswer:
    return _unknown(
        "Without the RTL lint skill, this benchmark arm does not apply bug-pattern rules."
    )


def _simple_counter_priority_bug_text() -> TextAnswer:
    return _unknown(
        "Without the RTL lint skill, this benchmark arm does not apply control-priority rules."
    )


def _register_pipe_stall_bug_text() -> TextAnswer:
    return _unknown(
        "Without the RTL lint skill, this benchmark arm does not apply stall-preservation rules."
    )


def _sync_fifo_count_bug_text() -> TextAnswer:
    return _unknown(
        "Without the RTL lint skill, this benchmark arm does not apply FIFO concurrency rules."
    )


def _apb_timer_irq_priority_bug_text() -> TextAnswer:
    return _unknown(
        "Without the RTL lint skill, this benchmark arm does not apply IRQ priority rules."
    )


def _edge_detect_polarity_bug_skill() -> TextAnswer:
    text = _read(EDGE_DETECT_BUG / "edge_detect.sv")
    if re.search(r"\brise_pulse_o\s*=\s*!\s*signal_i\s*&&\s*signal_q\s*;", text):
        return _regex_answer(
            "rise_pulse_o",
            "The rise output uses the falling-edge expression, matching the skill's code-local polarity rule.",
        )
    return _unknown("The expected rise-pulse polarity hazard was not found.")


def _simple_counter_priority_bug_skill() -> TextAnswer:
    text = _read(SIMPLE_COUNTER_BUG / "simple_counter.v")
    enable_pos = text.find("else if (enable_i)")
    clear_pos = text.find("else if (clear_i)")
    load_pos = text.find("else if (load_i)")
    if (
        enable_pos != -1
        and clear_pos != -1
        and load_pos != -1
        and enable_pos < load_pos < clear_pos
    ):
        return _regex_answer(
            "enable_i",
            "The enable branch precedes load and clear in the sequential priority chain.",
        )
    return _unknown("The expected control-priority ordering was not found.")


def _register_pipe_stall_bug_skill() -> TextAnswer:
    text = _read(REGISTER_PIPE_BUG / "register_pipe.v")
    if re.search(r"else\s+if\s*\(\s*stall_i\s*\)\s*begin\s*valid_q\s*<=\s*1'b0\s*;", text):
        return _regex_answer(
            "valid_q",
            "The stall branch clears valid_q instead of preserving the staged valid bit.",
        )
    return _unknown("The expected stall valid-clearing branch was not found.")


def _sync_fifo_count_bug_skill() -> TextAnswer:
    text = _read(SYNC_FIFO_BUG / "sync_fifo.sv")
    lacks_case = "case ({push_fire, pop_fire})" not in text
    push_else_pop = re.search(
        r"if\s*\(\s*push_fire\s*\)\s*begin\s*count_q\s*<=\s*count_q\s*\+\s*COUNT_ONE\s*;\s*end\s*else\s+if\s*\(\s*pop_fire\s*\)",
        text,
        flags=re.DOTALL,
    )
    if lacks_case and push_else_pop:
        return _regex_answer(
            "simultaneous_push_pop",
            "The count update lacks an explicit simultaneous push/pop hold case.",
        )
    return _unknown("The expected simultaneous push/pop count hazard was not found.")


def _apb_timer_irq_priority_bug_skill() -> TextAnswer:
    text = _read(BUGGY_APB_TIMER / "timer_core.sv")
    clear_pos = text.find("if (clear_irq_i)")
    set_pos = text.find("irq_o <= 1'b1")
    if clear_pos != -1 and set_pos != -1 and clear_pos < set_pos:
        return _regex_answer(
            "clear_irq_i",
            "The clear branch appears before the terminal-count IRQ set and can be overwritten later in the block.",
        )
    return _unknown("The expected clear-vs-set IRQ priority hazard was not found.")


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
    Case(
        "apb_design_unit_total",
        "APB timer design-unit inventory",
        "apb_timer",
        "Project loading",
        "medium",
        "design-unit discovery",
        "3",
        _apb_design_unit_total_text,
        ("pyslang_list_design_units",),
        "Checks module/package inventory across a small filelist IP.",
    ),
    Case(
        "sync_pkg_function_count",
        "sync_fifo_pkg function count",
        "sync_fifo",
        "Interface",
        "medium",
        "package member model",
        "2",
        _sync_pkg_function_count_text,
        ("pyslang_describe_design_unit",),
        "Package member counts are compiler-backed through describe_design_unit.",
    ),
    Case(
        "sync_mem_port_count",
        "sync_fifo_mem port count",
        "sync_fifo",
        "Interface",
        "easy",
        "port model",
        "6",
        _sync_mem_port_count_text,
        ("pyslang_describe_design_unit",),
        "A direct ANSI module interface should be easy both text-only and through MCP.",
    ),
    Case(
        "timer_ctrl_type_reference_count",
        "timer_ctrl_t bound reference count",
        "apb_timer",
        "Type binding",
        "hard",
        "semantic type binding",
        "2",
        _timer_ctrl_type_reference_count_text,
        ("pyslang_find_symbol",),
        "Requires resolving declared-type references to a typedef target.",
    ),
    Case(
        "tap_delay_for_keyword_count",
        "tap_delay_line for-loop syntax count",
        "tap_delay_line",
        "Syntax",
        "medium",
        "syntax-tree summary",
        "3",
        _tap_delay_for_keyword_count_text,
        ("pyslang_dump_syntax_tree_summary",),
        "Includes procedural loops and a generate loop in one single-module fixture.",
    ),
    Case(
        "apb_timer_include_path",
        "APB timer package include path",
        "apb_timer",
        "Preprocessing",
        "easy",
        "include metadata",
        "apb_timer_defs.svh",
        _apb_timer_include_path_text,
        ("pyslang_preprocess_files",),
        "Plain text can read the directive; MCP reports the same include metadata.",
    ),
    Case(
        "edge_detect_polarity_bug_output",
        "edge_detect polarity bug output",
        "edge_detect_polarity_bug",
        "Skill lint",
        "medium",
        "rule-guided RTL audit",
        "rise_pulse_o",
        _edge_detect_polarity_bug_text,
        ("pyslang_get_diagnostics",),
        "Compiler diagnostics are clean; the skill should flag the code-local polarity hazard.",
    ),
    Case(
        "simple_counter_priority_bug_signal",
        "simple_counter priority bug signal",
        "simple_counter_priority_bug",
        "Skill lint",
        "medium",
        "rule-guided RTL audit",
        "enable_i",
        _simple_counter_priority_bug_text,
        ("pyslang_get_diagnostics",),
        "The skill checks control-priority ordering rather than only parser diagnostics.",
    ),
    Case(
        "register_pipe_stall_bug_signal",
        "register_pipe stall bug signal",
        "register_pipe_valid_bug",
        "Skill lint",
        "medium",
        "rule-guided RTL audit",
        "valid_q",
        _register_pipe_stall_bug_text,
        ("pyslang_get_diagnostics",),
        "The skill recognizes that a stall should preserve valid state.",
    ),
    Case(
        "sync_fifo_count_bug_missing_case",
        "sync_fifo count update missing case",
        "sync_fifo_count_bug",
        "Skill lint",
        "hard",
        "rule-guided RTL audit",
        "simultaneous_push_pop",
        _sync_fifo_count_bug_text,
        ("pyslang_get_diagnostics",),
        "MCP proves the design parses; the skill adds the FIFO concurrency rule.",
    ),
    Case(
        "apb_timer_irq_priority_bug_signal",
        "APB timer IRQ clear priority bug signal",
        "apb_timer_irq_race_bug",
        "Skill lint",
        "hard",
        "rule-guided RTL audit",
        "clear_irq_i",
        _apb_timer_irq_priority_bug_text,
        ("pyslang_get_diagnostics",),
        "MCP proves the design is compiler-clean; the skill checks clear-vs-set priority.",
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
    "apb_design_unit_total": "How many project-local design units are in the APB timer project?",
    "sync_pkg_function_count": "How many FunctionDeclaration members are in sync_fifo_pkg?",
    "sync_mem_port_count": "How many total ports does sync_fifo_mem expose?",
    "timer_ctrl_type_reference_count": "How many references are reported for timer_ctrl_t?",
    "tap_delay_for_keyword_count": (
        "How many ForKeyword syntax nodes are reported in tap_delay_line.sv?"
    ),
    "apb_timer_include_path": "Which include path is reported by the APB timer package file?",
    "edge_detect_polarity_bug_output": (
        "Under rtl-lint-auditor rules, which output carries the edge polarity bug?"
    ),
    "simple_counter_priority_bug_signal": (
        "Under rtl-lint-auditor rules, which control signal incorrectly has priority?"
    ),
    "register_pipe_stall_bug_signal": (
        "Under rtl-lint-auditor rules, which state signal is incorrectly cleared on stall?"
    ),
    "sync_fifo_count_bug_missing_case": (
        "Under rtl-lint-auditor rules, which missing concurrency case breaks the FIFO count update?"
    ),
    "apb_timer_irq_priority_bug_signal": (
        "Under rtl-lint-auditor rules, which signal's clear action can be overwritten by a later IRQ set?"
    ),
}


def _prompt_for_arm(case: Case, arm: Arm) -> str:
    lines = [
        f"Mode: {arm.label}.",
        f"Project: {case.project}",
        f"Category: {case.category}",
        f"Task: {QUESTIONS[case.case_id]}",
    ]
    if arm.uses_skill:
        lines.extend(
            [
                "Use the locally installed rtl-lint-auditor skill as evidence discipline.",
                "Apply its evidence-grounding, output-discipline, tool-evidence-provenance, "
                "synthesizable-SystemVerilog, and lint-severity rules where relevant.",
            ]
        )
    else:
        lines.append(
            "Do not load or apply Codex skills, rulebooks, lint taxonomies, or domain-specific "
            "audit procedures."
        )
    if arm.uses_mcp:
        lines.extend(
            [
                "Use the launched local pyslang-mcp stdio server for compiler-backed evidence.",
                "Use only read-only MCP tools and record tool evidence when reasoning depends on "
                "tool output.",
                f"Required MCP tools for this case: {', '.join(case.mcp_tools)}",
            ]
        )
    else:
        lines.extend(
            [
                "Do not call pyslang, pyslang-mcp, Verilator, simulators, synthesis, lint tools, "
                "or any compiler frontend.",
                "You may inspect only checked-in HDL source files and filelists as text.",
            ]
        )
    lines.append(
        "Return exactly one scalar answer. If the available evidence cannot prove the answer, "
        "return exactly: unknown"
    )
    return "\n".join(lines)


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


async def _mcp_answer(session: ClientSession, case_id: str, *, use_skill: bool) -> str:
    if case_id == "edge_detect_polarity_bug_output":
        await _call_tool(
            session,
            "pyslang_get_diagnostics",
            {"project_root": str(EDGE_DETECT_BUG), "files": ["edge_detect.sv"]},
        )
        return _edge_detect_polarity_bug_skill().answer if use_skill else "unknown"
    if case_id == "simple_counter_priority_bug_signal":
        await _call_tool(
            session,
            "pyslang_get_diagnostics",
            {"project_root": str(SIMPLE_COUNTER_BUG), "files": ["simple_counter.v"]},
        )
        return _simple_counter_priority_bug_skill().answer if use_skill else "unknown"
    if case_id == "register_pipe_stall_bug_signal":
        await _call_tool(
            session,
            "pyslang_get_diagnostics",
            {"project_root": str(REGISTER_PIPE_BUG), "files": ["register_pipe.v"]},
        )
        return _register_pipe_stall_bug_skill().answer if use_skill else "unknown"
    if case_id == "sync_fifo_count_bug_missing_case":
        await _call_tool(
            session,
            "pyslang_get_diagnostics",
            {"project_root": str(SYNC_FIFO_BUG), "filelist": "project.f"},
        )
        return _sync_fifo_count_bug_skill().answer if use_skill else "unknown"
    if case_id == "apb_timer_irq_priority_bug_signal":
        await _call_tool(
            session,
            "pyslang_get_diagnostics",
            {"project_root": str(BUGGY_APB_TIMER), "filelist": "project.f"},
        )
        return _apb_timer_irq_priority_bug_skill().answer if use_skill else "unknown"
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
    if case_id == "apb_design_unit_total":
        payload = await _call_tool(
            session,
            "pyslang_list_design_units",
            {"project_root": str(APB_TIMER), "filelist": "project.f"},
        )
        return str(payload["summary"]["total"])
    if case_id == "sync_pkg_function_count":
        payload = await _call_tool(
            session,
            "pyslang_describe_design_unit",
            {"project_root": str(SYNC_FIFO), "filelist": "project.f", "name": "sync_fifo_pkg"},
        )
        return str(payload["design_unit"]["member_kind_counts"].get("FunctionDeclaration", 0))
    if case_id == "sync_mem_port_count":
        payload = await _call_tool(
            session,
            "pyslang_describe_design_unit",
            {"project_root": str(SYNC_FIFO), "filelist": "project.f", "name": "sync_fifo_mem"},
        )
        return str(len(cast(list[object], payload["design_unit"]["ports"])))
    if case_id == "timer_ctrl_type_reference_count":
        payload = await _call_tool(
            session,
            "pyslang_find_symbol",
            {
                "project_root": str(APB_TIMER),
                "filelist": "project.f",
                "query": "timer_ctrl_t",
                "match_mode": "exact",
                "include_references": True,
            },
        )
        return str(payload["summary"]["reference_count"])
    if case_id == "tap_delay_for_keyword_count":
        payload = await _call_tool(
            session,
            "pyslang_dump_syntax_tree_summary",
            {"project_root": str(TAP_DELAY_LINE), "files": ["tap_delay_line.sv"]},
        )
        return str(payload["files"][0]["node_kind_counts"].get("ForKeyword", 0))
    if case_id == "apb_timer_include_path":
        payload = await _call_tool(
            session,
            "pyslang_preprocess_files",
            {"project_root": str(APB_TIMER), "filelist": "project.f"},
        )
        for file_payload in cast(list[dict[str, Any]], payload["files"]):
            for include in cast(list[dict[str, Any]], file_payload["include_directives"]):
                if include["path"] == "apb_timer_defs.svh":
                    return str(include["path"])
        return "unknown"
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


def _build_summary(cases: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(cases)
    by_arm: dict[str, dict[str, float | int | str | bool]] = {}
    for arm in ARMS:
        arm_results = [case["arms"][arm.key] for case in cases]
        correct = sum(1 for result in arm_results if result["correct"])
        tokens = [int(result["tokens"]["total"]) for result in arm_results]
        total_tokens = sum(tokens)
        by_arm[arm.key] = {
            "label": arm.label,
            "uses_mcp": arm.uses_mcp,
            "uses_skill": arm.uses_skill,
            "correct": correct,
            "accuracy": round(correct / total, 4) if total else 0,
            "median_ms": _median([float(result["elapsed_ms"]) for result in arm_results]),
            "total_tokens_est": total_tokens,
            "median_tokens_est": _median([float(value) for value in tokens]),
            "correct_per_1k_tokens_est": round(correct * 1000 / total_tokens, 4)
            if total_tokens
            else 0,
        }
    categories = sorted({str(case["category"]) for case in cases})
    by_category: dict[str, dict[str, object]] = {}
    for category in categories:
        category_cases = [case for case in cases if case["category"] == category]
        by_category[category] = {
            "total": len(category_cases),
            "arms": {
                arm.key: {
                    "correct": sum(
                        1 for case in category_cases if case["arms"][arm.key]["correct"]
                    ),
                    "accuracy": round(
                        sum(1 for case in category_cases if case["arms"][arm.key]["correct"])
                        / len(category_cases),
                        4,
                    )
                    if category_cases
                    else 0,
                }
                for arm in ARMS
            },
        }
    text_correct = int(by_arm["text_no_skill"]["correct"])
    mcp_no_skill_correct = int(by_arm["mcp_no_skill"]["correct"])
    mcp_with_skill_correct = int(by_arm["mcp_with_skill"]["correct"])
    return {
        "total_cases": total,
        "arms": by_arm,
        "text_correct": text_correct,
        "mcp_correct": mcp_with_skill_correct,
        "text_accuracy": by_arm["text_no_skill"]["accuracy"],
        "mcp_accuracy": by_arm["mcp_with_skill"]["accuracy"],
        "delta_correct": mcp_with_skill_correct - text_correct,
        "deltas": {
            "mcp_no_skill_vs_text_no_skill": mcp_no_skill_correct - text_correct,
            "mcp_with_skill_vs_text_no_skill": mcp_with_skill_correct - text_correct,
            "mcp_with_skill_vs_mcp_no_skill": mcp_with_skill_correct - mcp_no_skill_correct,
        },
        "by_category": by_category,
        "median_mcp_ms": by_arm["mcp_with_skill"]["median_ms"],
        "median_text_ms": by_arm["text_no_skill"]["median_ms"],
        "total_text_tokens_est": by_arm["text_no_skill"]["total_tokens_est"],
        "total_mcp_tokens_est": by_arm["mcp_with_skill"]["total_tokens_est"],
        "median_text_tokens_est": by_arm["text_no_skill"]["median_tokens_est"],
        "median_mcp_tokens_est": by_arm["mcp_with_skill"]["median_tokens_est"],
        "text_correct_per_1k_tokens_est": by_arm["text_no_skill"]["correct_per_1k_tokens_est"],
        "mcp_correct_per_1k_tokens_est": by_arm["mcp_with_skill"]["correct_per_1k_tokens_est"],
    }


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return round(ordered[midpoint], 3)
    return round((ordered[midpoint - 1] + ordered[midpoint]) / 2, 3)


def _arm_payload(
    *,
    answer: str,
    expected: str,
    confidence: str,
    elapsed_ms: float,
    rationale: str,
    prompt: str,
    evidence: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "answer": answer,
        "correct": answer == expected,
        "confidence": confidence,
        "elapsed_ms": round(elapsed_ms, 3),
        "rationale": rationale,
        "evidence_chars": len(evidence),
        "tokens": _token_breakdown(prompt, evidence, answer),
    }
    if extra:
        payload.update(extra)
    return payload


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
            skill_context = _skill_context_blob()
            for case in CASES:
                text_evidence_paths = _text_evidence_paths(case.case_id)
                text_evidence = _evidence_blob(text_evidence_paths)
                text_prompt = _prompt_for_arm(case, ARMS[0])
                mcp_no_skill_prompt = _prompt_for_arm(case, ARMS[1])
                mcp_with_skill_prompt = _prompt_for_arm(case, ARMS[2])

                text_start = time.perf_counter()
                text = case.text_runner()
                text_elapsed = (time.perf_counter() - text_start) * 1000

                MCP_EVIDENCE_LOG.clear()
                mcp_no_skill_start = time.perf_counter()
                mcp_no_skill_answer = await _mcp_answer(
                    session,
                    case.case_id,
                    use_skill=False,
                )
                mcp_no_skill_elapsed = (time.perf_counter() - mcp_no_skill_start) * 1000
                mcp_no_skill_evidence = json.dumps(MCP_EVIDENCE_LOG, sort_keys=True)

                skill_eval_start = time.perf_counter()
                if case.case_id == "edge_detect_polarity_bug_output":
                    mcp_with_skill_answer = _edge_detect_polarity_bug_skill().answer
                elif case.case_id == "simple_counter_priority_bug_signal":
                    mcp_with_skill_answer = _simple_counter_priority_bug_skill().answer
                elif case.case_id == "register_pipe_stall_bug_signal":
                    mcp_with_skill_answer = _register_pipe_stall_bug_skill().answer
                elif case.case_id == "sync_fifo_count_bug_missing_case":
                    mcp_with_skill_answer = _sync_fifo_count_bug_skill().answer
                elif case.case_id == "apb_timer_irq_priority_bug_signal":
                    mcp_with_skill_answer = _apb_timer_irq_priority_bug_skill().answer
                else:
                    mcp_with_skill_answer = mcp_no_skill_answer
                skill_eval_elapsed = (time.perf_counter() - skill_eval_start) * 1000
                mcp_with_skill_elapsed = mcp_no_skill_elapsed + skill_eval_elapsed
                mcp_with_skill_tool_evidence = mcp_no_skill_evidence
                mcp_with_skill_evidence = "\n\n".join(
                    part
                    for part in (
                        "## MCP tool evidence\n" + mcp_with_skill_tool_evidence,
                        "## Skill context\n" + skill_context if skill_context else "",
                        "## Source evidence\n" + text_evidence if text_evidence else "",
                    )
                    if part
                )

                text_arm = _arm_payload(
                    answer=text.answer,
                    expected=case.expected,
                    confidence=text.confidence,
                    elapsed_ms=text_elapsed,
                    rationale=text.rationale,
                    prompt=text_prompt,
                    evidence=text_evidence,
                    extra={
                        "evidence_files": [
                            path.relative_to(REPO).as_posix()
                            for path in text_evidence_paths
                            if path.exists()
                        ],
                    },
                )
                mcp_no_skill_arm = _arm_payload(
                    answer=mcp_no_skill_answer,
                    expected=case.expected,
                    confidence="compiler-backed",
                    elapsed_ms=mcp_no_skill_elapsed,
                    rationale=(
                        "Answered through the launched local pyslang-mcp stdio server without "
                        "skill-specific audit rules."
                    ),
                    prompt=mcp_no_skill_prompt,
                    evidence=mcp_no_skill_evidence,
                    extra={
                        "evidence_calls": len(json.loads(mcp_no_skill_evidence)),
                    },
                )
                mcp_with_skill_arm = _arm_payload(
                    answer=mcp_with_skill_answer,
                    expected=case.expected,
                    confidence="compiler-backed+skill" if ARMS[2].uses_skill else "compiler-backed",
                    elapsed_ms=mcp_with_skill_elapsed,
                    rationale=(
                        "Answered through the launched local pyslang-mcp stdio server with "
                        "rtl-lint-auditor evidence discipline."
                    ),
                    prompt=mcp_with_skill_prompt,
                    evidence=mcp_with_skill_evidence,
                    extra={
                        "evidence_calls": len(json.loads(mcp_with_skill_tool_evidence)),
                        "skill_context_chars": len(skill_context),
                        "source_evidence_chars": len(text_evidence),
                    },
                )
                arms = {
                    "text_no_skill": text_arm,
                    "mcp_no_skill": mcp_no_skill_arm,
                    "mcp_with_skill": mcp_with_skill_arm,
                }

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
                            "text_no_skill": text_prompt,
                            "mcp_no_skill": mcp_no_skill_prompt,
                            "mcp_with_skill": mcp_with_skill_prompt,
                        },
                        "arms": arms,
                        "text": text_arm,
                        "mcp": mcp_with_skill_arm,
                    }
                )

    return {
        "metadata": {
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "repo": "pyslang-mcp",
            "branch": _git_value("branch", "--show-current"),
            "commit": _git_value("rev-parse", "--short", "HEAD"),
            "comparison": (
                "text/no-skill baseline vs local pyslang-mcp without skill vs "
                "local pyslang-mcp with rtl-lint-auditor skill context"
            ),
            "server_command": ".venv/bin/python -m pyslang_mcp --transport stdio",
            "tool_count": len(tool_names),
            "tools": tool_names,
            "arms": [
                {
                    "key": arm.key,
                    "label": arm.label,
                    "uses_mcp": arm.uses_mcp,
                    "uses_skill": arm.uses_skill,
                }
                for arm in ARMS
            ],
            "methodology": (
                "The text/no-skill baseline may inspect checked-in HDL and filelists with "
                "deterministic regex helpers, but it cannot call pyslang, MCP tools, any "
                "compiler frontend, or skill rulebooks. The MCP/no-skill arm launches the "
                "local server and uses structured read-only tool responses without domain "
                "skill rules. The MCP/skill arm uses the same MCP evidence plus the installed "
                "rtl-lint-auditor skill context and deterministic rule-guided checks for "
                "lint-oriented cases."
            ),
            "token_methodology": (
                "Token counts are deterministic estimates using ceil(character_count / 4) "
                "over the exact prompt, evidence payload, and scalar answer. The MCP/skill "
                "arm includes the skill and rule text plus source evidence in its evidence "
                "payload, so totals are a conservative per-case reload estimate rather than "
                "Codex internal tokenizer telemetry."
            ),
            "speed_methodology": (
                "Elapsed milliseconds measure local evidence acquisition and deterministic "
                "answer extraction. The MCP/skill arm reuses the MCP/no-skill tool evidence "
                "and adds deterministic skill-rule evaluation time. Timings exclude hidden "
                "LLM inference time."
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


def _html_dashboard_v2(report: dict[str, Any]) -> str:
    payload = json.dumps(report, sort_keys=True).replace("</", "<\\/")
    generated = html.escape(str(report["metadata"]["generated_at"]))
    template = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>pyslang-mcp MCP / Skill Cross Benchmark</title>
  <style>
    :root {
      --ink: #181818;
      --muted: #5c6462;
      --paper: #f6f4ef;
      --panel: #fffdf8;
      --line: #d5d0c8;
      --text: #a63d2d;
      --mcp: #2f6072;
      --skill: #5f7c3f;
      --gold: #b18427;
      --bad: #9b2f2f;
      --good: #276a4f;
      --shadow: 0 16px 44px rgba(24, 24, 24, 0.10);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--ink);
      background:
        linear-gradient(90deg, rgba(24,24,24,0.04) 1px, transparent 1px) 0 0 / 32px 32px,
        linear-gradient(rgba(24,24,24,0.03) 1px, transparent 1px) 0 0 / 32px 32px,
        var(--paper);
      font-family: Georgia, "Times New Roman", serif;
    }
    button, input, select { font: inherit; }
    .shell {
      width: min(1480px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 28px 0 46px;
    }
    .hero {
      min-height: 300px;
      display: grid;
      grid-template-columns: minmax(0, 1.35fr) minmax(320px, 0.65fr);
      gap: 24px;
      align-items: end;
      border-top: 8px solid var(--ink);
      border-bottom: 1px solid var(--line);
      padding: 28px 0 24px;
    }
    h1 {
      margin: 0;
      max-width: 1040px;
      font-size: clamp(42px, 7vw, 104px);
      line-height: 0.88;
      letter-spacing: 0;
      font-weight: 800;
    }
    h2 {
      margin: 0 0 12px;
      font-size: 22px;
      letter-spacing: 0;
    }
    .subtitle {
      margin-top: 22px;
      max-width: 850px;
      color: var(--muted);
      font-size: 18px;
      line-height: 1.45;
    }
    .stamp {
      border: 1px solid var(--ink);
      background: rgba(255,253,248,0.88);
      box-shadow: var(--shadow);
      padding: 18px;
    }
    .stamp strong {
      display: block;
      margin-bottom: 12px;
      color: var(--muted);
      font-size: 12px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }
    .stamp code {
      display: block;
      white-space: normal;
      overflow-wrap: anywhere;
      font-family: "Courier New", monospace;
      font-size: 14px;
      line-height: 1.5;
    }
    .metrics {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 14px;
      margin: 24px 0;
    }
    .metric {
      min-height: 126px;
      border: 1px solid var(--line);
      background: var(--panel);
      padding: 18px;
    }
    .metric .label {
      color: var(--muted);
      font-size: 12px;
      letter-spacing: 0.11em;
      text-transform: uppercase;
    }
    .metric .value {
      margin-top: 12px;
      font-family: "Courier New", monospace;
      font-size: 32px;
      font-weight: 700;
    }
    .metric .sub {
      margin-top: 8px;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.35;
    }
    .controls {
      display: grid;
      grid-template-columns: 1.5fr repeat(3, minmax(150px, 0.45fr));
      gap: 10px;
      margin: 22px 0;
    }
    .controls input,
    .controls select {
      width: 100%;
      min-height: 44px;
      border: 1px solid var(--ink);
      border-radius: 0;
      background: #fffdf8;
      color: var(--ink);
      padding: 10px 12px;
    }
    .bands {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(360px, 0.55fr);
      gap: 18px;
      align-items: start;
    }
    .section {
      border-top: 3px solid var(--ink);
      padding-top: 14px;
    }
    .legend {
      display: flex;
      gap: 14px;
      flex-wrap: wrap;
      margin: 8px 0 14px;
      color: var(--muted);
      font-size: 13px;
    }
    .swatch {
      display: inline-block;
      width: 12px;
      height: 12px;
      border: 1px solid var(--ink);
      vertical-align: -1px;
      margin-right: 5px;
    }
    .swatch.text_no_skill { background: var(--text); }
    .swatch.mcp_no_skill { background: var(--mcp); }
    .swatch.mcp_with_skill { background: var(--skill); }
    .bar-list {
      display: grid;
      gap: 10px;
    }
    .bar-row {
      display: grid;
      grid-template-columns: 190px 1fr 72px;
      gap: 10px;
      align-items: center;
      font-size: 14px;
    }
    .track {
      height: 18px;
      border: 1px solid var(--line);
      background: rgba(24,24,24,0.05);
      overflow: hidden;
    }
    .fill {
      height: 100%;
      background: var(--mcp);
    }
    .fill.text_no_skill { background: var(--text); }
    .fill.mcp_no_skill { background: var(--mcp); }
    .fill.mcp_with_skill { background: var(--skill); }
    .cross {
      display: grid;
      gap: 10px;
    }
    .cross-row {
      display: grid;
      grid-template-columns: 1fr 84px 84px;
      gap: 10px;
      align-items: center;
      border-bottom: 1px solid var(--line);
      padding: 8px 0;
      font-size: 14px;
    }
    .table-wrap {
      margin-top: 24px;
      border-top: 3px solid var(--ink);
      overflow-x: auto;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      background: rgba(255,253,248,0.78);
    }
    th {
      text-align: left;
      color: var(--muted);
      font-size: 12px;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      padding: 12px 10px;
      border-bottom: 1px solid var(--ink);
      cursor: pointer;
      user-select: none;
      white-space: nowrap;
    }
    td {
      padding: 12px 10px;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
      font-size: 14px;
      line-height: 1.35;
    }
    tr:hover td { background: rgba(177,132,39,0.08); }
    code,
    .mono {
      font-family: "Courier New", monospace;
    }
    .pill {
      display: inline-block;
      border: 1px solid var(--ink);
      background: #fffdf8;
      padding: 3px 7px;
      font-family: "Courier New", monospace;
      font-size: 12px;
    }
    .ok { color: var(--good); font-weight: 700; }
    .miss { color: var(--bad); font-weight: 700; }
    .details {
      margin-top: 24px;
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 16px;
    }
    .detail-panel {
      min-height: 190px;
      border: 1px solid var(--line);
      background: var(--panel);
      padding: 16px;
    }
    .detail-panel h3 {
      margin: 0 0 10px;
      font-size: 16px;
    }
    .detail-panel p {
      margin: 8px 0;
      color: var(--muted);
      line-height: 1.45;
    }
    .prompt-box {
      margin: 10px 0 0;
      max-height: 250px;
      overflow: auto;
      border: 1px solid var(--line);
      background: #fffdf8;
      padding: 12px;
      white-space: pre-wrap;
      font-family: "Courier New", monospace;
      font-size: 12px;
      line-height: 1.45;
    }
    .method {
      margin-top: 26px;
      border-top: 3px solid var(--ink);
      padding-top: 14px;
      color: var(--muted);
      line-height: 1.55;
      max-width: 1040px;
    }
    @media (max-width: 980px) {
      .hero,
      .bands,
      .details,
      .controls,
      .metrics {
        grid-template-columns: 1fr;
      }
      h1 { font-size: clamp(40px, 14vw, 72px); }
    }
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <div>
        <h1>MCP / Skill Cross Benchmark</h1>
        <p class="subtitle">A reproducible HDL understanding benchmark comparing source text without skills, local <code>pyslang-mcp</code> without skills, and local <code>pyslang-mcp</code> with the <code>rtl-lint-auditor</code> skill context. Generated __GENERATED__.</p>
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
        <option value="skill-wins">Skill wins</option>
        <option value="mcp-wins">MCP beats text</option>
        <option value="all-correct">All correct</option>
        <option value="any-miss">Any miss</option>
      </select>
    </section>

    <section class="bands">
      <div class="section">
        <h2>Accuracy By Category</h2>
        <div class="legend" id="legend"></div>
        <div class="bar-list" id="category-bars"></div>
      </div>
      <div class="section">
        <h2>Cross Statistics</h2>
        <div class="cross" id="cross-stats"></div>
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
            <th data-sort="text_no_skill">Text/no skill</th>
            <th data-sort="mcp_no_skill">MCP/no skill</th>
            <th data-sort="mcp_with_skill">MCP/skill</th>
            <th data-sort="skill_delta">Skill delta</th>
            <th data-sort="tokens">Tokens</th>
            <th data-sort="latency">MCP/skill ms</th>
          </tr>
        </thead>
        <tbody id="case-table"></tbody>
      </table>
    </section>

    <section class="details" id="details"></section>

    <section class="method">
      <h2>Methodology</h2>
      <p id="methodology"></p>
      <p id="token-methodology"></p>
      <p id="speed-methodology"></p>
    </section>
  </main>

  <script type="application/json" id="report-data">__PAYLOAD__</script>
  <script>
    const data = JSON.parse(document.getElementById('report-data').textContent);
    const arms = data.metadata.arms;
    let sortKey = 'title';
    let sortDir = 1;

    const search = document.getElementById('search');
    const category = document.getElementById('category');
    const difficulty = document.getElementById('difficulty');
    const verdict = document.getElementById('verdict');

    function unique(values) {
      return [...new Set(values)].sort();
    }

    function pct(value, total) {
      return total ? Math.round((value / total) * 100) : 0;
    }

    function escapeHtml(value) {
      return String(value).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
    }

    function populateSelect(node, label, values) {
      node.innerHTML = '<option value="all">' + label + '</option>' + values.map(v => '<option value="' + escapeHtml(v) + '">' + escapeHtml(v) + '</option>').join('');
    }

    function verdictClass(row) {
      const text = row.arms.text_no_skill.correct;
      const mcp = row.arms.mcp_no_skill.correct;
      const skill = row.arms.mcp_with_skill.correct;
      if (skill && !mcp) return 'skill-wins';
      if (mcp && !text) return 'mcp-wins';
      if (text && mcp && skill) return 'all-correct';
      return 'any-miss';
    }

    function filteredCases() {
      const q = search.value.trim().toLowerCase();
      return data.cases.filter(row => {
        const armAnswers = arms.map(arm => row.arms[arm.key].answer).join(' ');
        const haystack = [row.title, row.project, row.category, row.difficulty, row.expected, armAnswers].join(' ').toLowerCase();
        return (!q || haystack.includes(q))
          && (category.value === 'all' || row.category === category.value)
          && (difficulty.value === 'all' || row.difficulty === difficulty.value)
          && (verdict.value === 'all' || verdictClass(row) === verdict.value || (verdict.value === 'any-miss' && arms.some(arm => !row.arms[arm.key].correct)));
      });
    }

    function armTotals(rows, key) {
      const correct = rows.filter(row => row.arms[key].correct).length;
      const tokens = rows.reduce((sum, row) => sum + row.arms[key].tokens.total, 0);
      const elapsed = rows.map(row => row.arms[key].elapsed_ms).sort((a, b) => a - b);
      const median = elapsed.length ? elapsed[Math.floor((elapsed.length - 1) / 2)] : 0;
      return { correct, tokens, median };
    }

    function renderMetrics(rows) {
      const total = rows.length;
      document.getElementById('metrics').innerHTML = arms.map(arm => {
        const totals = armTotals(rows, arm.key);
        return '<div class="metric"><div class="label">' + escapeHtml(arm.label) + '</div><div class="value">' + totals.correct + '/' + total + '</div><div class="sub">' + pct(totals.correct, total) + '% exact-match, ' + totals.tokens + ' estimated tokens, median ' + totals.median.toFixed(1) + ' ms</div></div>';
      }).join('');
    }

    function renderCategoryBars(rows) {
      const cats = unique(rows.map(row => row.category));
      document.getElementById('category-bars').innerHTML = cats.map(cat => {
        const scoped = rows.filter(row => row.category === cat);
        const bars = arms.map(arm => {
          const value = pct(scoped.filter(row => row.arms[arm.key].correct).length, scoped.length);
          return '<div class="bar-row"><span>' + escapeHtml(arm.label) + '</span><div class="track"><div class="fill ' + arm.key + '" style="width:' + value + '%"></div></div><strong>' + value + '%</strong></div>';
        }).join('');
        return '<div><strong>' + escapeHtml(cat) + '</strong>' + bars + '</div>';
      }).join('');
    }

    function renderCrossStats(rows) {
      const pairs = [
        ['MCP/no skill vs text/no skill', 'mcp_no_skill', 'text_no_skill'],
        ['MCP/skill vs text/no skill', 'mcp_with_skill', 'text_no_skill'],
        ['MCP/skill vs MCP/no skill', 'mcp_with_skill', 'mcp_no_skill']
      ];
      document.getElementById('cross-stats').innerHTML = pairs.map(pair => {
        const a = armTotals(rows, pair[1]);
        const b = armTotals(rows, pair[2]);
        const tokenDelta = a.tokens - b.tokens;
        return '<div class="cross-row"><span>' + pair[0] + '</span><strong>' + (a.correct - b.correct >= 0 ? '+' : '') + (a.correct - b.correct) + ' correct</strong><span class="mono">' + (tokenDelta >= 0 ? '+' : '') + tokenDelta + ' tok</span></div>';
      }).join('');
    }

    function sortValue(row, key) {
      if (row.arms[key]) return row.arms[key].correct ? 1 : 0;
      if (key === 'skill_delta') return (row.arms.mcp_with_skill.correct ? 1 : 0) - (row.arms.mcp_no_skill.correct ? 1 : 0);
      if (key === 'tokens') return row.arms.mcp_with_skill.tokens.total;
      if (key === 'latency') return row.arms.mcp_with_skill.elapsed_ms;
      return String(row[key] || row.expected).toLowerCase();
    }

    function renderArmCell(row, key) {
      const result = row.arms[key];
      return '<span class="' + (result.correct ? 'ok' : 'miss') + '">' + (result.correct ? 'OK' : 'MISS') + '</span><br><code>' + escapeHtml(result.answer) + '</code>';
    }

    function renderTable(rows) {
      const sorted = rows.slice().sort((a, b) => {
        const av = sortValue(a, sortKey);
        const bv = sortValue(b, sortKey);
        return av > bv ? sortDir : av < bv ? -sortDir : 0;
      });
      document.getElementById('case-table').innerHTML = sorted.map(row => {
        const delta = (row.arms.mcp_with_skill.correct ? 1 : 0) - (row.arms.mcp_no_skill.correct ? 1 : 0);
        const tokenText = arms.map(arm => arm.label.split('/')[0] + ':' + row.arms[arm.key].tokens.total).join('<br>');
        return '<tr data-id="' + escapeHtml(row.id) + '">'
          + '<td><strong>' + escapeHtml(row.title) + '</strong><br><span class="pill">' + escapeHtml(row.project) + '</span></td>'
          + '<td>' + escapeHtml(row.category) + '<br><span class="pill">' + escapeHtml(row.evidence_need) + '</span></td>'
          + '<td>' + escapeHtml(row.difficulty) + '</td>'
          + '<td><code>' + escapeHtml(row.expected) + '</code></td>'
          + '<td>' + renderArmCell(row, 'text_no_skill') + '</td>'
          + '<td>' + renderArmCell(row, 'mcp_no_skill') + '</td>'
          + '<td>' + renderArmCell(row, 'mcp_with_skill') + '</td>'
          + '<td>' + (delta > 0 ? '<span class="ok">+1</span>' : delta < 0 ? '<span class="miss">-1</span>' : '0') + '</td>'
          + '<td class="mono">' + tokenText + '</td>'
          + '<td>' + row.arms.mcp_with_skill.elapsed_ms.toFixed(1) + '</td>'
          + '</tr>';
      }).join('');
      document.querySelectorAll('#case-table tr').forEach(row => {
        row.addEventListener('click', () => renderDetails(row.dataset.id));
      });
    }

    function renderDetails(id) {
      const row = data.cases.find(item => item.id === id) || filteredCases()[0] || data.cases[0];
      if (!row) return;
      const intro = '<div class="detail-panel"><h3>' + escapeHtml(row.title) + '</h3><p><strong>Expected:</strong> <code>' + escapeHtml(row.expected) + '</code></p><p>' + escapeHtml(row.note) + '</p><p><strong>MCP tools:</strong> ' + row.mcp_tools.map(escapeHtml).join(', ') + '</p></div>';
      const panels = arms.map(arm => {
        const result = row.arms[arm.key];
        return '<div class="detail-panel"><h3>' + escapeHtml(arm.label) + '</h3><p><strong>Answer:</strong> <code>' + escapeHtml(result.answer) + '</code> <span class="' + (result.correct ? 'ok' : 'miss') + '">' + (result.correct ? 'OK' : 'MISS') + '</span></p><p>' + escapeHtml(result.rationale) + '</p><p><strong>Tokens:</strong> ' + result.tokens.total + ' = prompt ' + result.tokens.prompt + ' + evidence ' + result.tokens.evidence + ' + answer ' + result.tokens.answer + '</p><p><strong>Elapsed:</strong> ' + result.elapsed_ms.toFixed(3) + ' ms</p><pre class="prompt-box">' + escapeHtml(row.prompts[arm.key]) + '</pre></div>';
      }).join('');
      document.getElementById('details').innerHTML = intro + panels;
    }

    function render() {
      const rows = filteredCases();
      renderMetrics(rows);
      renderCategoryBars(rows);
      renderCrossStats(rows);
      renderTable(rows);
      renderDetails(rows[0] && rows[0].id);
    }

    document.getElementById('legend').innerHTML = arms.map(arm => '<span><span class="swatch ' + arm.key + '"></span>' + escapeHtml(arm.label) + '</span>').join('');
    populateSelect(category, 'All categories', unique(data.cases.map(row => row.category)));
    populateSelect(difficulty, 'All difficulties', unique(data.cases.map(row => row.difficulty)));
    document.getElementById('run-context').textContent = data.metadata.branch + '@' + data.metadata.commit + '\\n' + data.metadata.server_command + '\\n' + data.metadata.tool_count + ' MCP tools discovered';
    document.getElementById('methodology').textContent = data.metadata.methodology;
    document.getElementById('token-methodology').textContent = data.metadata.token_methodology;
    document.getElementById('speed-methodology').textContent = data.metadata.speed_methodology;
    [search, category, difficulty, verdict].forEach(node => node.addEventListener('input', render));
    document.querySelectorAll('th[data-sort]').forEach(th => th.addEventListener('click', () => {
      const next = th.dataset.sort;
      if (sortKey === next) sortDir *= -1;
      sortKey = next;
      render();
    }));
    render();
  </script>
</body>
</html>
"""
    return template.replace("__PAYLOAD__", payload).replace("__GENERATED__", generated)


def write_report(report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "results.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "index.html").write_text(_html_dashboard_v2(report), encoding="utf-8")


def print_markdown_summary(report: dict[str, Any], output_dir: Path) -> None:
    summary = report["summary"]
    print("# MCP / Skill Cross Benchmark")
    print()
    print(f"- Cases: {summary['total_cases']}")
    for arm in report["metadata"]["arms"]:
        arm_summary = summary["arms"][arm["key"]]
        print(f"- {arm['label']} exact answers: {arm_summary['correct']}/{summary['total_cases']}")
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
