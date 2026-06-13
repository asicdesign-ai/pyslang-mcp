#!/usr/bin/env python3
"""Run isolated Codex A/B evals over the repository's RTL benchmark cases."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pyslang_mcp.server import PUBLIC_TOOL_NAMES

if __package__:
    from scripts import run_mcp_comparison as deterministic
else:
    import run_mcp_comparison as deterministic

REPO = Path(__file__).resolve().parents[1]
SKILL_DIR = REPO / "skills" / "pyslang-verilog-context"
DEFAULT_MODEL = "gpt-5.5"
DEFAULT_REASONING_EFFORT = "xhigh"
DEFAULT_TRIALS = 3
DEFAULT_JOBS = 2
ANSWER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low", "unknown"],
        },
        "evidence": {"type": "array", "items": {"type": "string"}},
        "limitations": {"type": "array", "items": {"type": "string"}},
        "tools_used": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["answer", "confidence", "evidence", "limitations", "tools_used"],
    "additionalProperties": False,
}


class Arm(StrEnum):
    NO_SKILL_NO_MCP = "no_skill_no_mcp"
    SKILL_MCP = "skill_mcp"


@dataclass(frozen=True, slots=True)
class EvalCase:
    case_id: str
    title: str
    project: str
    question: str
    expected: str
    required_tools: tuple[str, ...]
    source_root: Path
    project_args: dict[str, Any]


def normalize_answer(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def build_codex_command(
    *,
    arm: Arm,
    codex_bin: str,
    workspace: Path,
    schema_path: Path,
    output_path: Path,
    model: str,
    reasoning_effort: str,
) -> list[str]:
    command = [
        codex_bin,
        "exec",
        "--json",
        "--color",
        "never",
        "--sandbox",
        "read-only",
        "--config",
        'approval_policy="never"',
        "--ephemeral",
        "--ignore-rules",
        "--cd",
        str(workspace),
        "--model",
        model,
        "--config",
        f'model_reasoning_effort="{reasoning_effort}"',
        "--output-schema",
        str(schema_path),
        "--output-last-message",
        str(output_path),
    ]
    if arm is Arm.NO_SKILL_NO_MCP:
        command.append("--ignore-user-config")
    return command


def summarize_trials(
    case: EvalCase,
    arm: Arm,
    trials: list[dict[str, Any]],
) -> dict[str, Any]:
    answers = [normalize_answer(trial.get("answer")) for trial in trials]
    correct_trials = sum(bool(trial.get("correct")) for trial in trials)
    successful_trials = sum(trial.get("status") == "ok" for trial in trials)
    required_tool_trials = sum(
        all(tool in set(trial.get("tools_used", [])) for tool in case.required_tools)
        for trial in trials
    )
    total = len(trials)
    return {
        "arm": arm.value,
        "trial_count": total,
        "successful_trials": successful_trials,
        "correct_trials": correct_trials,
        "accuracy": correct_trials / total if total else 0.0,
        "answers": answers,
        "consistent": len(set(answers)) <= 1,
        "required_tools": list(case.required_tools),
        "required_tool_trials": required_tool_trials,
        "required_tool_rate": required_tool_trials / total if total else 0.0,
        "trials": trials,
    }


def _project_spec(project: str) -> tuple[Path, dict[str, Any]]:
    specs: dict[str, tuple[Path, dict[str, Any]]] = {
        "sync_fifo": (
            deterministic.SYNC_FIFO,
            {"filelist": "project.f", "top_modules": ["sync_fifo"]},
        ),
        "apb_timer": (
            deterministic.APB_TIMER,
            {"filelist": "project.f", "top_modules": ["apb_timer"]},
        ),
        "apb_timer_irq_race_bug": (
            deterministic.BUGGY_APB_TIMER,
            {"filelist": "project.f", "top_modules": ["apb_timer"]},
        ),
        "tests/fixtures/broken": (
            deterministic.BROKEN_FIXTURE,
            {"files": ["broken.sv"], "top_modules": ["broken"]},
        ),
        "tests/fixtures/multi_file": (
            deterministic.MULTI_FILE_FIXTURE,
            {"filelist": "project.f", "top_modules": ["top"]},
        ),
        "tap_delay_line": (
            deterministic.TAP_DELAY_LINE,
            {"files": ["tap_delay_line.sv"], "top_modules": ["tap_delay_line"]},
        ),
    }
    return specs[project]


def load_cases() -> tuple[EvalCase, ...]:
    cases: list[EvalCase] = []
    for case in deterministic.CASES:
        if case.category == "Skill lint":
            continue
        source_root, project_args = _project_spec(case.project)
        cases.append(
            EvalCase(
                case_id=case.case_id,
                title=case.title,
                project=case.project,
                question=deterministic.QUESTIONS[case.case_id],
                expected=case.expected,
                required_tools=case.mcp_tools,
                source_root=source_root,
                project_args=project_args,
            )
        )

    verilog_debug = REPO / "tests" / "fixtures" / "verilog_debug"
    broken = REPO / "tests" / "fixtures" / "broken"
    cases.extend(
        (
            EvalCase(
                case_id="diagnostic_group_code",
                title="Grouped diagnostic code",
                project="verilog_debug_diagnostics",
                question=("What diagnostic code is reported for the single diagnostic group?"),
                expected="DiagCode(UndeclaredIdentifier)",
                required_tools=("pyslang_summarize_diagnostics_by_code",),
                source_root=broken,
                project_args={"files": ["broken.sv"], "top_modules": ["broken"]},
            ),
            EvalCase(
                case_id="member_kind",
                title="Local member kind",
                project="verilog_debug",
                question=("Inside debug_stage, what member kind is response_pop_fifo__rdy?"),
                expected="variable",
                required_tools=("pyslang_find_member",),
                source_root=verilog_debug,
                project_args={"filelist": "project.f", "top_modules": ["debug_top"]},
            ),
            EvalCase(
                case_id="assignment_rhs",
                title="Assignment RHS",
                project="verilog_debug",
                question=(
                    "What is the exact RHS snippet of the assignment driving "
                    "debug_stage.response__vld?"
                ),
                expected="stage_enable",
                required_tools=("pyslang_get_assignments",),
                source_root=verilog_debug,
                project_args={"filelist": "project.f", "top_modules": ["debug_top"]},
            ),
            EvalCase(
                case_id="instance_output_actual",
                title="Instance output actual path",
                project="verilog_debug",
                question=(
                    "For debug_top.u_stage, what connected-symbol hierarchical path is bound "
                    "to output port response__vld?"
                ),
                expected="debug_top.response__vld",
                required_tools=("pyslang_get_instance_connections",),
                source_root=verilog_debug,
                project_args={"filelist": "project.f", "top_modules": ["debug_top"]},
            ),
            EvalCase(
                case_id="connectivity_stage_output",
                title="Connectivity stage output",
                project="verilog_debug",
                question=(
                    "When tracing loads from debug_top.ctrl_out__rdy, which debug_stage output "
                    "signal is reached before crossing back to debug_top?"
                ),
                expected="debug_top.u_stage.response__vld",
                required_tools=("pyslang_trace_connectivity",),
                source_root=verilog_debug,
                project_args={"filelist": "project.f", "top_modules": ["debug_top"]},
            ),
        )
    )
    return tuple(cases)


def _project_args_text(project_args: dict[str, Any]) -> str:
    payload = {"project_root": "project", **project_args}
    return json.dumps(payload, sort_keys=True)


def build_prompt(case: EvalCase, arm: Arm) -> str:
    lines = [
        f"Task: {case.question}",
        "The checked-in RTL project is under the workspace path `project`.",
        f"Project arguments: {_project_args_text(case.project_args)}",
    ]
    if arm is Arm.NO_SKILL_NO_MCP:
        lines.extend(
            (
                "This is the no-skill, no-MCP arm. Do not load or apply any Codex skill.",
                "Do not use MCP, pyslang, Verilator, simulators, synthesis, lint, formal, or any "
                "compiler frontend. Inspect only the files under `project` as text.",
            )
        )
    else:
        lines.extend(
            (
                "Use $pyslang-verilog-context for this task.",
                "Use the configured local pyslang-mcp server and call the required tool(s): "
                + ", ".join(case.required_tools),
                "Keep all MCP operations read-only and state frontend-evidence limitations.",
            )
        )
    lines.extend(
        (
            "Return only the JSON object required by the output schema.",
            "Set `answer` to exactly one scalar string. If the permitted evidence cannot prove "
            "the answer, set `answer` to `unknown`.",
            "List tools actually called in `tools_used`; use an empty list if none were called.",
        )
    )
    return "\n".join(lines)


def _prepare_codex_home(
    *,
    arm: Arm,
    codex_home: Path,
    workspace: Path,
    auth_source: Path,
) -> None:
    codex_home.mkdir(parents=True)
    if not auth_source.is_file():
        raise FileNotFoundError(f"Codex auth file not found: {auth_source}")
    (codex_home / "auth.json").symlink_to(auth_source)
    installation_id = auth_source.parent / "installation_id"
    if installation_id.is_file():
        (codex_home / "installation_id").symlink_to(installation_id)
    if arm is Arm.NO_SKILL_NO_MCP:
        return

    skills_dir = codex_home / "skills"
    skills_dir.mkdir()
    (skills_dir / "pyslang-verilog-context").symlink_to(SKILL_DIR, target_is_directory=True)
    server_python = REPO / ".venv" / "bin" / "python"
    enabled_tools = sorted(f'"{tool_name}"' for tool_name in PUBLIC_TOOL_NAMES.values())
    config = "\n".join(
        (
            f'model = "{DEFAULT_MODEL}"',
            f'model_reasoning_effort = "{DEFAULT_REASONING_EFFORT}"',
            "",
            "[mcp_servers.pyslang_mcp]",
            f'command = "{server_python.as_posix()}"',
            'args = ["-m", "pyslang_mcp", "--transport", "stdio"]',
            f'cwd = "{workspace.as_posix()}"',
            "required = true",
            'default_tools_approval_mode = "auto"',
            f"enabled_tools = [{', '.join(enabled_tools)}]",
            "startup_timeout_sec = 30",
            "tool_timeout_sec = 120",
            "",
        )
    )
    (codex_home / "config.toml").write_text(config, encoding="utf-8")


def _initialize_workspace(case: EvalCase, workspace: Path) -> None:
    shutil.copytree(case.source_root, workspace / "project")
    subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
    subprocess.run(["git", "config", "user.name", "Codex Eval"], cwd=workspace, check=True)
    subprocess.run(
        ["git", "config", "user.email", "codex-eval@example.invalid"],
        cwd=workspace,
        check=True,
    )
    subprocess.run(["git", "add", "project"], cwd=workspace, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "eval fixture"],
        cwd=workspace,
        check=True,
    )


def _parse_events(stdout: str) -> tuple[list[str], dict[str, int]]:
    tools: list[str] = []
    usage: dict[str, int] = {}
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "turn.completed" and isinstance(event.get("usage"), dict):
            usage = {
                str(key): int(value)
                for key, value in event["usage"].items()
                if isinstance(value, int)
            }
        item = event.get("item")
        if not isinstance(item, dict) or item.get("type") != "mcp_tool_call":
            continue
        tool = item.get("tool") or item.get("name")
        if isinstance(tool, str) and tool not in tools:
            tools.append(tool)
    return tools, usage


def _sanitize(value: Any, workspace: Path) -> Any:
    marker = workspace.parent.as_posix()
    if isinstance(value, str):
        return value.replace(marker, "<eval-temp>")
    if isinstance(value, list):
        return [_sanitize(item, workspace) for item in value]
    if isinstance(value, dict):
        return {str(key): _sanitize(item, workspace) for key, item in value.items()}
    return value


def run_trial(
    *,
    case: EvalCase,
    arm: Arm,
    trial: int,
    codex_bin: str,
    model: str,
    reasoning_effort: str,
    timeout_seconds: int,
    auth_source: Path,
) -> dict[str, Any]:
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="pyslang-codex-eval-") as temp_dir:
        temp = Path(temp_dir)
        workspace = temp / "workspace"
        workspace.mkdir()
        _initialize_workspace(case, workspace)
        schema_path = temp / "answer.schema.json"
        output_path = temp / "answer.json"
        schema_path.write_text(json.dumps(ANSWER_SCHEMA), encoding="utf-8")
        codex_home = temp / "codex-home"
        _prepare_codex_home(
            arm=arm,
            codex_home=codex_home,
            workspace=workspace,
            auth_source=auth_source,
        )
        command = build_codex_command(
            arm=arm,
            codex_bin=codex_bin,
            workspace=workspace,
            schema_path=schema_path,
            output_path=output_path,
            model=model,
            reasoning_effort=reasoning_effort,
        )
        env = {**os.environ, "CODEX_HOME": str(codex_home)}
        try:
            completed = subprocess.run(
                [*command, build_prompt(case, arm)],
                cwd=workspace,
                env=env,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return {
                "trial": trial,
                "status": "timeout",
                "answer": "",
                "correct": False,
                "tools_used": [],
                "usage": {},
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "error": f"Codex timed out after {exc.timeout} seconds",
            }

        event_tools, usage = _parse_events(completed.stdout)
        if completed.returncode != 0 or not output_path.is_file():
            return {
                "trial": trial,
                "status": "error",
                "answer": "",
                "correct": False,
                "tools_used": event_tools,
                "usage": usage,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "error": _sanitize(completed.stderr[-2000:], workspace),
            }
        try:
            payload = json.loads(output_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return {
                "trial": trial,
                "status": "invalid_output",
                "answer": "",
                "correct": False,
                "tools_used": event_tools,
                "usage": usage,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "error": str(exc),
            }

        answer = normalize_answer(payload.get("answer"))
        declared_tools = [
            str(tool) for tool in payload.get("tools_used", []) if isinstance(tool, str)
        ]
        tools_used = sorted(set(event_tools) | set(declared_tools))
        return {
            "trial": trial,
            "status": "ok",
            "answer": answer,
            "correct": answer == case.expected,
            "confidence": payload.get("confidence"),
            "evidence": _sanitize(payload.get("evidence", []), workspace),
            "limitations": _sanitize(payload.get("limitations", []), workspace),
            "tools_used": tools_used,
            "event_tools": event_tools,
            "usage": usage,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        }


def _aggregate(cases: list[dict[str, Any]], trials_per_arm: int) -> dict[str, Any]:
    arm_summary: dict[str, Any] = {}
    for arm in Arm:
        summaries = [case["arms"][arm.value] for case in cases]
        total_trials = sum(int(summary["trial_count"]) for summary in summaries)
        correct_trials = sum(int(summary["correct_trials"]) for summary in summaries)
        consistent_cases = sum(bool(summary["consistent"]) for summary in summaries)
        required_tool_trials = sum(int(summary["required_tool_trials"]) for summary in summaries)
        arm_summary[arm.value] = {
            "case_count": len(summaries),
            "trials_per_case": trials_per_arm,
            "total_trials": total_trials,
            "correct_trials": correct_trials,
            "accuracy": correct_trials / total_trials if total_trials else 0.0,
            "consistent_cases": consistent_cases,
            "consistency_rate": consistent_cases / len(summaries) if summaries else 0.0,
            "required_tool_trials": required_tool_trials,
            "required_tool_rate": (required_tool_trials / total_trials if total_trials else 0.0),
        }
    return arm_summary


def write_report(report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "results.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# Codex Verilog Context A/B Eval",
        "",
        f"Generated: {report['generated_at']}",
        f"Model: `{report['model']}` (`{report['reasoning_effort']}` reasoning)",
        f"Trials per case and arm: {report['trials_per_case']}",
        "",
        "| Arm | Correct trials | Accuracy | Consistent cases | Required-tool rate |",
        "|---|---:|---:|---:|---:|",
    ]
    for arm in Arm:
        summary = report["summary"][arm.value]
        lines.append(
            "| {arm} | {correct}/{total} | {accuracy:.1%} | {consistent}/{cases} | "
            "{tool_rate:.1%} |".format(
                arm=arm.value,
                correct=summary["correct_trials"],
                total=summary["total_trials"],
                accuracy=summary["accuracy"],
                consistent=summary["consistent_cases"],
                cases=summary["case_count"],
                tool_rate=summary["required_tool_rate"],
            )
        )
    lines.extend(("", "## Cases", ""))
    for case in report["cases"]:
        lines.append(f"### {case['id']}: {case['title']}")
        lines.append("")
        lines.append(f"Expected: `{case['expected']}`")
        lines.append("")
        for arm in Arm:
            summary = case["arms"][arm.value]
            lines.append(
                f"- `{arm.value}`: {summary['correct_trials']}/{summary['trial_count']} correct; "
                f"answers={summary['answers']}; consistent={summary['consistent']}"
            )
        lines.append("")
    (output_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    cases = list(load_cases())
    selected = set(args.case or [])
    if selected:
        cases = [case for case in cases if case.case_id in selected]
        missing = selected - {case.case_id for case in cases}
        if missing:
            raise ValueError(f"Unknown case ids: {', '.join(sorted(missing))}")
    if args.list_cases:
        for case in cases:
            print(case.case_id)
        return 0

    auth_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    auth_source = auth_home / "auth.json"
    jobs: list[tuple[EvalCase, Arm, int]] = [
        (case, arm, trial) for case in cases for arm in Arm for trial in range(1, args.trials + 1)
    ]
    trial_results: dict[tuple[str, str], list[dict[str, Any]]] = {
        (case.case_id, arm.value): [] for case in cases for arm in Arm
    }

    with ThreadPoolExecutor(max_workers=args.jobs) as executor:
        future_map = {
            executor.submit(
                run_trial,
                case=case,
                arm=arm,
                trial=trial,
                codex_bin=args.codex_bin,
                model=args.model,
                reasoning_effort=args.reasoning_effort,
                timeout_seconds=args.timeout_seconds,
                auth_source=auth_source,
            ): (case, arm, trial)
            for case, arm, trial in jobs
        }
        for future in as_completed(future_map):
            case, arm, trial = future_map[future]
            try:
                result = future.result()
            except Exception as exc:
                result = {
                    "trial": trial,
                    "status": "error",
                    "answer": "",
                    "correct": False,
                    "tools_used": [],
                    "usage": {},
                    "elapsed_seconds": 0.0,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            trial_results[(case.case_id, arm.value)].append(result)
            print(
                f"[{case.case_id}] {arm.value} trial {trial}: "
                f"{result['status']} answer={result.get('answer', '')!r}"
            )

    report_cases: list[dict[str, Any]] = []
    for case in cases:
        arms: dict[str, Any] = {}
        for arm in Arm:
            trials = sorted(
                trial_results[(case.case_id, arm.value)],
                key=lambda result: int(result["trial"]),
            )
            arms[arm.value] = summarize_trials(case, arm, trials)
        report_cases.append(
            {
                "id": case.case_id,
                "title": case.title,
                "project": case.project,
                "question": case.question,
                "expected": case.expected,
                "required_tools": list(case.required_tools),
                "project_args": case.project_args,
                "arms": arms,
            }
        )

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "repo_commit": subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip(),
        "model": args.model,
        "reasoning_effort": args.reasoning_effort,
        "trials_per_case": args.trials,
        "case_count": len(report_cases),
        "methodology": (
            "Isolated Codex homes and read-only temporary git workspaces. The no-skill/no-MCP "
            "arm has no skills or MCP config and is instructed to inspect RTL text only. The "
            "skill+MCP arm exposes only pyslang-verilog-context and the local read-only "
            "pyslang-mcp stdio server."
        ),
        "summary": _aggregate(report_cases, args.trials),
        "cases": report_cases,
    }
    write_report(report, args.output_dir)
    print(f"wrote Codex A/B report to {args.output_dir}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO / "reports" / f"codex_ab_{datetime.now(UTC):%Y%m%d}",
    )
    parser.add_argument("--case", action="append", help="Run one case id; repeatable.")
    parser.add_argument("--trials", type=int, default=DEFAULT_TRIALS)
    parser.add_argument("--jobs", type=int, default=DEFAULT_JOBS)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--reasoning-effort", default=DEFAULT_REASONING_EFFORT)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument("--list-cases", action="store_true")
    args = parser.parse_args()
    if args.trials < 1:
        parser.error("--trials must be at least 1")
    if args.jobs < 1:
        parser.error("--jobs must be at least 1")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
