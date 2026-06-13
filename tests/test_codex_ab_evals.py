from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.run_codex_ab_evals import (  # noqa: E402
    Arm,
    EvalCase,
    build_codex_command,
    normalize_answer,
    summarize_trials,
)


def test_normalize_answer_handles_scalar_json_values() -> None:
    assert normalize_answer("  WIDTH=8\n") == "WIDTH=8"
    assert normalize_answer(6) == "6"
    assert normalize_answer(None) == ""


def test_build_codex_command_isolates_no_skill_arm(tmp_path: Path) -> None:
    command = build_codex_command(
        arm=Arm.NO_SKILL_NO_MCP,
        codex_bin="codex",
        workspace=tmp_path / "workspace",
        schema_path=tmp_path / "schema.json",
        output_path=tmp_path / "answer.json",
        model="gpt-5.5",
        reasoning_effort="xhigh",
    )

    assert "--ignore-user-config" in command
    assert "--ignore-rules" in command
    assert "--sandbox" in command
    assert "read-only" in command
    assert 'approval_policy="never"' in command
    assert "--ask-for-approval" not in command
    assert "--ephemeral" in command
    assert "--output-schema" in command


def test_summarize_trials_reports_accuracy_consistency_and_tool_compliance() -> None:
    case = EvalCase(
        case_id="example",
        title="Example",
        project="example",
        question="What is the answer?",
        expected="42",
        required_tools=("pyslang_find_member",),
        source_root=Path("project"),
        project_args={"files": ["example.sv"]},
    )
    trials = [
        {
            "answer": "42",
            "correct": True,
            "tools_used": ["pyslang_find_member"],
            "status": "ok",
        },
        {
            "answer": "42",
            "correct": True,
            "tools_used": ["pyslang_find_member"],
            "status": "ok",
        },
        {
            "answer": "unknown",
            "correct": False,
            "tools_used": [],
            "status": "ok",
        },
    ]

    summary = summarize_trials(case, Arm.SKILL_MCP, trials)

    assert summary["correct_trials"] == 2
    assert summary["accuracy"] == 2 / 3
    assert summary["consistent"] is False
    assert summary["required_tool_trials"] == 2
    assert summary["required_tool_rate"] == 2 / 3
