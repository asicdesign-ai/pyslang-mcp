#!/usr/bin/env python3
"""Run a 75-case public RTL comparison over cloned upstream repositories."""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from mcp.types import CallToolResult

from pyslang_mcp.cache import AnalysisCache
from pyslang_mcp.server import PUBLIC_TOOL_NAMES, create_server


REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = Path(__file__).resolve().parent
CORPUS_ROOT = REPORT_DIR / "repos"
SKILL_PATH = REPO_ROOT / "skills" / "pyslang-verilog-context" / "SKILL.md"
OUT_JSON = REPORT_DIR / "results.json"
OUT_MD = REPORT_DIR / "summary.md"

HDL_SUFFIXES = {".sv", ".v"}
TARGET_CASE_COUNT = 75

REPOS = [
    {
        "id": "lowrisc-ibex",
        "url": "https://github.com/lowRISC/ibex",
        "license": "Apache-2.0",
        "subdirs": ["rtl", "shared/rtl"],
        "target": 15,
    },
    {
        "id": "pulp-common-cells",
        "url": "https://github.com/pulp-platform/common_cells",
        "license": "Solderpad-0.51",
        "subdirs": ["src"],
        "target": 15,
    },
    {
        "id": "verilog-axis",
        "url": "https://github.com/alexforencich/verilog-axis",
        "license": "MIT",
        "subdirs": ["rtl"],
        "target": 15,
    },
    {
        "id": "pulp-axi",
        "url": "https://github.com/pulp-platform/axi",
        "license": "Solderpad-0.51",
        "subdirs": ["src"],
        "target": 15,
    },
    {
        "id": "pulp-register-interface",
        "url": "https://github.com/pulp-platform/register_interface",
        "license": "Solderpad-0.51",
        "subdirs": ["src"],
        "target": 14,
    },
    {
        "id": "picorv32",
        "url": "https://github.com/YosysHQ/picorv32",
        "license": "ISC",
        "subdirs": ["."],
        "target": 1,
    },
]


@dataclass(frozen=True)
class SourceFile:
    repo_id: str
    repo_url: str
    license: str
    commit: str
    repo_root: Path
    relpath: str
    line_count: int
    byte_count: int


@dataclass(frozen=True)
class Case:
    case_id: str
    task: str
    source: SourceFile


def _git_value(repo_root: Path, *args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(repo_root), *args],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//.*", "", text)


def _design_unit_names(text: str) -> list[tuple[str, str]]:
    cleaned = _strip_comments(text)
    matches = re.findall(
        r"\b(module|interface|package)\s+([A-Za-z_][A-Za-z0-9_$]*)",
        cleaned,
    )
    return [(kind, name) for kind, name in matches if name not in {"automatic"}]


def _find_matching(text: str, open_index: int) -> int | None:
    depth = 0
    for idx in range(open_index, len(text)):
        char = text[idx]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return idx
    return None


def _skip_ws(text: str, index: int) -> int:
    while index < len(text) and text[index].isspace():
        index += 1
    return index


def _split_top_level_commas(text: str) -> list[str]:
    parts: list[str] = []
    start = 0
    paren = bracket = brace = 0
    for idx, char in enumerate(text):
        if char == "(":
            paren += 1
        elif char == ")":
            paren = max(0, paren - 1)
        elif char == "[":
            bracket += 1
        elif char == "]":
            bracket = max(0, bracket - 1)
        elif char == "{":
            brace += 1
        elif char == "}":
            brace = max(0, brace - 1)
        elif char == "," and paren == 0 and bracket == 0 and brace == 0:
            parts.append(text[start:idx])
            start = idx + 1
    parts.append(text[start:])
    return [part.strip() for part in parts if part.strip()]


def _text_port_count(text: str, unit_name: str) -> str:
    cleaned = _strip_comments(text)
    match = re.search(rf"\b(?:module|interface)\s+{re.escape(unit_name)}\b", cleaned)
    if not match:
        return "unknown"
    index = _skip_ws(cleaned, match.end())
    if index < len(cleaned) and cleaned[index] == "#":
        index = _skip_ws(cleaned, index + 1)
        if index >= len(cleaned) or cleaned[index] != "(":
            return "unknown"
        close = _find_matching(cleaned, index)
        if close is None:
            return "unknown"
        index = _skip_ws(cleaned, close + 1)
    if index >= len(cleaned) or cleaned[index] != "(":
        return "0"
    close = _find_matching(cleaned, index)
    if close is None:
        return "unknown"
    ports = _split_top_level_commas(cleaned[index + 1 : close])
    return str(len(ports))


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def _source_evidence(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[:20000]


def _skill_context() -> str:
    if not SKILL_PATH.exists():
        return ""
    return SKILL_PATH.read_text(encoding="utf-8", errors="replace")


def discover_sources() -> list[SourceFile]:
    selected: list[SourceFile] = []
    for repo in REPOS:
        repo_root = CORPUS_ROOT / cast(str, repo["id"])
        if not repo_root.is_dir():
            raise FileNotFoundError(f"missing cloned repo: {repo_root}")
        commit = _git_value(repo_root, "rev-parse", "--short", "HEAD")
        candidates: list[Path] = []
        for subdir in cast(list[str], repo["subdirs"]):
            root = repo_root if subdir == "." else repo_root / subdir
            if not root.exists():
                continue
            candidates.extend(
                path
                for path in sorted(root.rglob("*"))
                if path.is_file()
                and path.suffix in HDL_SUFFIXES
                and path.stat().st_size <= 220_000
            )
        filtered = []
        for path in candidates:
            rel = path.relative_to(repo_root).as_posix()
            lowered = f"/{rel.lower()}"
            if any(skip in lowered for skip in ("/test/", "/tests/", "/tb/", "/dv/")):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if not _design_unit_names(text):
                continue
            filtered.append(path)
        for path in filtered[: cast(int, repo["target"]) * 3]:
            rel = path.relative_to(repo_root).as_posix()
            text = path.read_text(encoding="utf-8", errors="replace")
            selected.append(
                SourceFile(
                    repo_id=cast(str, repo["id"]),
                    repo_url=cast(str, repo["url"]),
                    license=cast(str, repo["license"]),
                    commit=commit,
                    repo_root=repo_root,
                    relpath=rel,
                    line_count=text.count("\n") + 1,
                    byte_count=path.stat().st_size,
                )
            )
    if len(selected) < TARGET_CASE_COUNT:
        raise RuntimeError(f"need at least {TARGET_CASE_COUNT} files, selected {len(selected)}")
    return selected


def build_cases(sources: list[SourceFile]) -> list[Case]:
    tasks = ("diagnostic_status", "design_unit_total", "first_unit_port_count")
    return [
        Case(case_id=f"real75-{idx + 1:03d}-{source.repo_id}-{Path(source.relpath).stem}", task=tasks[idx % len(tasks)], source=source)
        for idx, source in enumerate(sources)
    ]


async def call_tool(server: Any, tool_name: str, arguments: dict[str, Any]) -> tuple[dict[str, Any], bool, float]:
    start = time.perf_counter()
    result = await server.call_tool(tool_name, arguments)
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert isinstance(result, CallToolResult)
    structured = cast(dict[str, Any], result.structuredContent or {})
    payload = cast(dict[str, Any], structured.get("result", structured))
    return payload, bool(result.isError), elapsed_ms


def project_args(source: SourceFile) -> dict[str, Any]:
    return {
        "project_root": str(source.repo_root),
        "files": [source.relpath],
    }


def first_unit(units_payload: dict[str, Any]) -> dict[str, Any] | None:
    units = cast(list[dict[str, Any]], units_payload.get("design_units", []))
    if not units:
        return None
    return units[0]


def text_answer(case: Case, expected_meta: dict[str, Any]) -> dict[str, Any]:
    path = case.source.repo_root / case.source.relpath
    text = path.read_text(encoding="utf-8", errors="replace")
    units = _design_unit_names(text)
    start = time.perf_counter()
    if case.task == "diagnostic_status":
        answer = "unknown"
        rationale = "Text-only reading cannot prove parser/semantic diagnostic status."
    elif case.task == "design_unit_total":
        answer = str(len(units))
        rationale = "Regex counted visible module/interface/package declarations."
    else:
        unit_name = str(expected_meta.get("unit_name") or (units[0][1] if units else ""))
        answer = _text_port_count(text, unit_name) if unit_name else "unknown"
        rationale = "Text parser counted the first visible module/interface port list."
    elapsed_ms = (time.perf_counter() - start) * 1000
    evidence = _source_evidence(path)
    return {
        "answer": answer,
        "correct": answer == expected_meta["expected"],
        "elapsed_ms": round(elapsed_ms, 3),
        "rationale": rationale,
        "tokens": {
            "evidence": _estimate_tokens(evidence),
            "answer": _estimate_tokens(answer),
            "total": _estimate_tokens(evidence) + _estimate_tokens(answer),
        },
    }


async def mcp_answer(server: Any, case: Case, *, with_skill: bool) -> dict[str, Any]:
    args = project_args(case.source)
    tool_calls: list[str] = []
    elapsed_ms = 0.0

    if with_skill:
        _, parse_error, parse_ms = await call_tool(server, PUBLIC_TOOL_NAMES["parse_files"], args)
        tool_calls.append("pyslang_parse_files")
        elapsed_ms += parse_ms
        diagnostics, diag_error, diag_ms = await call_tool(server, PUBLIC_TOOL_NAMES["get_diagnostics"], args)
        tool_calls.append("pyslang_get_diagnostics")
        elapsed_ms += diag_ms
    else:
        parse_error = diag_error = False
        diagnostics = {}

    if case.task == "diagnostic_status":
        if not with_skill:
            diagnostics, diag_error, diag_ms = await call_tool(
                server, PUBLIC_TOOL_NAMES["get_diagnostics"], args
            )
            tool_calls.append("pyslang_get_diagnostics")
            elapsed_ms += diag_ms
        answer = str(diagnostics.get("project_status", {}).get("status", "unknown"))
        evidence = json.dumps(diagnostics, sort_keys=True)[:20000]
    else:
        units_payload, units_error, units_ms = await call_tool(
            server, PUBLIC_TOOL_NAMES["list_design_units"], args
        )
        tool_calls.append("pyslang_list_design_units")
        elapsed_ms += units_ms
        unit = first_unit(units_payload)
        if case.task == "design_unit_total":
            answer = str(units_payload.get("summary", {}).get("total", "unknown"))
            evidence = json.dumps(units_payload, sort_keys=True)[:20000]
        elif unit is not None:
            describe_payload, describe_error, describe_ms = await call_tool(
                server,
                PUBLIC_TOOL_NAMES["describe_design_unit"],
                {**args, "name": unit["name"]},
            )
            tool_calls.append("pyslang_describe_design_unit")
            elapsed_ms += describe_ms
            ports = cast(
                list[dict[str, Any]],
                describe_payload.get("design_unit", {}).get("ports", []),
            )
            answer = str(len(ports)) if not describe_error else "unknown"
            evidence = json.dumps(describe_payload, sort_keys=True)[:20000]
        else:
            answer = "unknown"
            evidence = json.dumps(units_payload, sort_keys=True)[:20000]

    skill_blob = _skill_context() if with_skill else ""
    return {
        "answer": answer,
        "elapsed_ms": round(elapsed_ms, 3),
        "tool_calls": tool_calls,
        "tool_call_count": len(tool_calls),
        "had_tool_error": bool(parse_error or diag_error),
        "tokens": {
            "evidence": _estimate_tokens(evidence),
            "skill": _estimate_tokens(skill_blob),
            "answer": _estimate_tokens(answer),
            "total": _estimate_tokens(evidence) + _estimate_tokens(skill_blob) + _estimate_tokens(answer),
        },
    }


async def expected_for_case(server: Any, case: Case) -> dict[str, Any] | None:
    args = project_args(case.source)
    if case.task == "diagnostic_status":
        diagnostics, is_error, _ = await call_tool(server, PUBLIC_TOOL_NAMES["get_diagnostics"], args)
        if is_error:
            return None
        return {
            "expected": str(diagnostics.get("project_status", {}).get("status", "unknown")),
            "unit_name": None,
        }

    units_payload, is_error, _ = await call_tool(server, PUBLIC_TOOL_NAMES["list_design_units"], args)
    if is_error:
        return None
    unit = first_unit(units_payload)
    if case.task == "design_unit_total":
        return {
            "expected": str(units_payload.get("summary", {}).get("total", "unknown")),
            "unit_name": unit.get("name") if unit else None,
        }
    if unit is None:
        return None
    describe_payload, describe_error, _ = await call_tool(
        server,
        PUBLIC_TOOL_NAMES["describe_design_unit"],
        {**args, "name": unit["name"]},
    )
    if describe_error:
        return None
    ports = cast(list[dict[str, Any]], describe_payload.get("design_unit", {}).get("ports", []))
    return {"expected": str(len(ports)), "unit_name": unit["name"]}


def summarize(cases: list[dict[str, Any]]) -> dict[str, Any]:
    arms = ("text_no_skill", "mcp_no_skill", "skill_mcp")
    summary: dict[str, Any] = {
        "total_cases": len(cases),
        "arms": {},
        "by_task": {},
        "by_repo": {},
    }
    for arm in arms:
        correct = sum(1 for case in cases if case["arms"][arm]["correct"])
        elapsed = sorted(case["arms"][arm]["elapsed_ms"] for case in cases)
        tokens = sum(case["arms"][arm]["tokens"]["total"] for case in cases)
        summary["arms"][arm] = {
            "correct": correct,
            "accuracy": round(correct / len(cases), 4) if cases else 0.0,
            "median_ms": elapsed[len(elapsed) // 2] if elapsed else 0.0,
            "total_tokens_est": tokens,
        }
    for key in ("task", "repo_id"):
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for case in cases:
            groups[case[key]].append(case)
        target = "by_task" if key == "task" else "by_repo"
        for group, items in sorted(groups.items()):
            summary[target][group] = {
                "total": len(items),
                "arms": {
                    arm: {
                        "correct": sum(1 for item in items if item["arms"][arm]["correct"]),
                        "accuracy": round(
                            sum(1 for item in items if item["arms"][arm]["correct"]) / len(items),
                            4,
                        ),
                    }
                    for arm in arms
                },
            }
    summary["deltas"] = {
        "mcp_no_skill_vs_text_no_skill": summary["arms"]["mcp_no_skill"]["correct"]
        - summary["arms"]["text_no_skill"]["correct"],
        "skill_mcp_vs_mcp_no_skill": summary["arms"]["skill_mcp"]["correct"]
        - summary["arms"]["mcp_no_skill"]["correct"],
        "skill_mcp_vs_text_no_skill": summary["arms"]["skill_mcp"]["correct"]
        - summary["arms"]["text_no_skill"]["correct"],
    }
    return summary


def markdown_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Real Public RTL 75-Case Comparison",
        "",
        f"Generated: {report['metadata']['generated_at']}",
        "",
        "## Sources",
        "",
        "| Repo | Commit | License | Cases |",
        "|---|---|---|---:|",
    ]
    repo_counts = Counter(case["repo_id"] for case in report["cases"])
    for repo in report["metadata"]["sources"]:
        lines.append(
            f"| `{repo['id']}` | `{repo['commit']}` | {repo['license']} | {repo_counts[repo['id']]} |"
        )
    lines.extend(
        [
            "",
            "## Overall",
            "",
            "| Arm | Correct | Accuracy | Median local evidence time | Est. tokens |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    labels = {
        "text_no_skill": "Text/no skill",
        "mcp_no_skill": "MCP/no skill",
        "skill_mcp": "Skill + MCP",
    }
    total = summary["total_cases"]
    for arm, label in labels.items():
        item = summary["arms"][arm]
        lines.append(
            f"| {label} | {item['correct']}/{total} | {item['accuracy']:.0%} | {item['median_ms']:.3f} ms | {item['total_tokens_est']:,} |"
        )
    lines.extend(
        [
            "",
            "## By Task",
            "",
            "| Task | Cases | Text/no skill | MCP/no skill | Skill + MCP |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for task, item in summary["by_task"].items():
        lines.append(
            f"| `{task}` | {item['total']} | {item['arms']['text_no_skill']['correct']}/{item['total']} | {item['arms']['mcp_no_skill']['correct']}/{item['total']} | {item['arms']['skill_mcp']['correct']}/{item['total']} |"
        )
    lines.extend(
        [
            "",
            "## By Repo",
            "",
            "| Repo | Cases | Text/no skill | MCP/no skill | Skill + MCP |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for repo_id, item in summary["by_repo"].items():
        lines.append(
            f"| `{repo_id}` | {item['total']} | {item['arms']['text_no_skill']['correct']}/{item['total']} | {item['arms']['mcp_no_skill']['correct']}/{item['total']} | {item['arms']['skill_mcp']['correct']}/{item['total']} |"
        )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- These are real public RTL source files, but the questions are deterministic scalar probes.",
            "- Expected answers are compiler-backed `pyslang-mcp` observations, so this is an MCP-grounded reading benchmark rather than an independent human-labeled benchmark.",
            "- Skill + MCP follows the `pyslang-verilog-context` discipline by parsing and checking diagnostics before structural queries.",
            "- On these reading tasks, Skill + MCP and MCP/no skill have the same exact-answer accuracy; the skill mainly adds sequencing and limitation discipline rather than new RTL bug rules.",
            "",
            "## Verification Strategy",
            "",
            "The 75-case run is verified with this process:",
            "",
            "1. Clone public upstream RTL repositories under `reports/real_examples_75/repos/`.",
            "2. Record each repository commit and license in the report.",
            "3. Select real `.sv` and `.v` files from implementation-oriented directories",
            "   with file-size limits to keep the local compiler-backed run bounded.",
            "4. Skip files where a deterministic expected answer cannot be derived from",
            "   `pyslang-mcp`.",
            "5. Run three arms per accepted case:",
            "   - Text/no skill: local source-text heuristics only.",
            "   - MCP/no skill: targeted `pyslang-mcp` tool calls.",
            "   - Skill + MCP: parse and diagnostics first, then the structural query.",
            "6. Score exact scalar answers against compiler-backed observations.",
            "7. Run `py_compile` on `run_real75_comparison.py` after generation.",
            "",
            "This is a real-source frontend-reading benchmark. It is not a blind autonomous",
            "LLM-judge benchmark and does not claim simulation, synthesis, CDC/RDC, timing,",
            "formal, or full lint signoff.",
        ]
    )
    return "\n".join(lines) + "\n"


async def main_async() -> dict[str, Any]:
    sources = discover_sources()
    server = create_server(cache=AnalysisCache())
    report_cases: list[dict[str, Any]] = []
    used_sources: set[tuple[str, str]] = set()
    tasks = ("diagnostic_status", "design_unit_total", "first_unit_port_count")

    async def try_add_case(source: SourceFile) -> bool:
        case_index = len(report_cases) + 1
        case = Case(
            case_id=f"real75-{case_index:03d}-{source.repo_id}-{Path(source.relpath).stem}",
            task=tasks[(case_index - 1) % len(tasks)],
            source=source,
        )
        expected_meta = await expected_for_case(server, case)
        if expected_meta is None:
            return False
        text = text_answer(case, expected_meta)
        mcp = await mcp_answer(server, case, with_skill=False)
        skill = await mcp_answer(server, case, with_skill=True)
        mcp["correct"] = mcp["answer"] == expected_meta["expected"]
        skill["correct"] = skill["answer"] == expected_meta["expected"]
        report_cases.append(
            {
                "id": case.case_id,
                "task": case.task,
                "repo_id": case.source.repo_id,
                "source": case.source.relpath,
                "line_count": case.source.line_count,
                "byte_count": case.source.byte_count,
                "expected": expected_meta["expected"],
                "unit_name": expected_meta.get("unit_name"),
                "arms": {
                    "text_no_skill": text,
                    "mcp_no_skill": mcp,
                    "skill_mcp": skill,
                },
            }
        )
        used_sources.add((source.repo_id, source.relpath))
        return True

    sources_by_repo: dict[str, list[SourceFile]] = defaultdict(list)
    for source in sources:
        sources_by_repo[source.repo_id].append(source)

    for repo in REPOS:
        repo_id = cast(str, repo["id"])
        target = cast(int, repo["target"])
        accepted_for_repo = 0
        for source in sources_by_repo[repo_id]:
            if accepted_for_repo >= target:
                break
            if (source.repo_id, source.relpath) in used_sources:
                continue
            if await try_add_case(source):
                accepted_for_repo += 1

    if len(report_cases) < TARGET_CASE_COUNT:
        for source in sources:
            if len(report_cases) >= TARGET_CASE_COUNT:
                break
            if (source.repo_id, source.relpath) in used_sources:
                continue
            await try_add_case(source)

    if len(report_cases) != TARGET_CASE_COUNT:
        raise RuntimeError(f"accepted {len(report_cases)} valid cases, expected {TARGET_CASE_COUNT}")
    source_metadata = []
    for repo in REPOS:
        repo_root = CORPUS_ROOT / cast(str, repo["id"])
        source_metadata.append(
            {
                "id": repo["id"],
                "url": repo["url"],
                "license": repo["license"],
                "commit": _git_value(repo_root, "rev-parse", "--short", "HEAD"),
            }
        )
    return {
        "metadata": {
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "comparison": "75 real public RTL files: text/no-skill vs MCP/no-skill vs pyslang-verilog-context skill+MCP",
            "repo": "pyslang-mcp",
            "sources": source_metadata,
            "skill": str(SKILL_PATH.relative_to(REPO_ROOT)),
            "methodology": (
                "Each case uses one real public HDL file. Tasks cycle through frontend diagnostic status, "
                "design-unit inventory, and first design-unit port count. Text/no-skill uses local text heuristics. "
                "MCP/no-skill uses targeted pyslang-mcp tools. Skill+MCP uses parse + diagnostics before the structural query."
            ),
        },
        "summary": summarize(report_cases),
        "cases": report_cases,
    }


def main() -> int:
    report = asyncio.run(main_async())
    OUT_JSON.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    OUT_MD.write_text(markdown_report(report), encoding="utf-8")
    summary = report["summary"]
    print("# Real Public RTL 75-Case Comparison")
    print()
    for arm, label in (
        ("text_no_skill", "Text/no skill"),
        ("mcp_no_skill", "MCP/no skill"),
        ("skill_mcp", "Skill + MCP"),
    ):
        item = summary["arms"][arm]
        print(f"- {label}: {item['correct']}/{summary['total_cases']} ({item['accuracy']:.0%})")
    print(f"- JSON: {OUT_JSON}")
    print(f"- Markdown: {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
