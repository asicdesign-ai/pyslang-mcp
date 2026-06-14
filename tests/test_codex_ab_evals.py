from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts import run_codex_ab_evals as codex_ab  # noqa: E402
from scripts.run_codex_ab_evals import (  # noqa: E402
    Arm,
    EvalCase,
    _completed_trial_results,
    _failure_message,
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
    for feature in ("apps", "plugins", "plugin_sharing", "tool_suggest"):
        assert ["--disable", feature] in [
            command[index : index + 2] for index in range(len(command) - 1)
        ]


def test_run_trial_closes_inherited_stdin(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    case = EvalCase(
        case_id="example",
        title="Example",
        project="example",
        question="What is the answer?",
        expected="42",
        required_tools=(),
        source_root=tmp_path,
        project_args={"files": ["example.sv"]},
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(codex_ab, "_initialize_workspace", lambda *_args: None)

    def prepare_home(**kwargs: object) -> None:
        codex_home = kwargs["codex_home"]
        assert isinstance(codex_home, Path)
        codex_home.mkdir()

    monkeypatch.setattr(codex_ab, "_prepare_codex_home", prepare_home)

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.update(kwargs)
        output_index = command.index("--output-last-message") + 1
        Path(command[output_index]).write_text(
            json.dumps(
                {
                    "answer": "42",
                    "confidence": "high",
                    "evidence": [],
                    "limitations": [],
                    "tools_used": [],
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(codex_ab.subprocess, "run", fake_run)

    result = codex_ab.run_trial(
        case=case,
        arm=Arm.NO_SKILL_NO_MCP,
        trial=1,
        codex_bin="codex",
        model="gpt-5.5",
        reasoning_effort="xhigh",
        timeout_seconds=30,
        auth_source=tmp_path / "auth.json",
    )

    assert result["status"] == "ok"
    assert captured["stdin"] is subprocess.DEVNULL


def test_failure_message_includes_json_stdout_error(tmp_path: Path) -> None:
    completed = subprocess.CompletedProcess(
        ["codex", "exec"],
        1,
        stdout=(
            '{"type":"error","message":"usage limit reached; retry later"}\n'
            '{"type":"turn.failed","error":{"message":"usage limit reached"}}\n'
        ),
        stderr="Reading additional input from stdin...\n",
    )

    message = _failure_message(completed, tmp_path / "workspace")

    assert "return code: 1" in message
    assert "usage limit reached; retry later" in message
    assert "Reading additional input from stdin" in message


def test_completed_trial_results_keeps_only_successful_requested_trials() -> None:
    report = {
        "model": "gpt-5.5",
        "reasoning_effort": "xhigh",
        "trials_per_case": 3,
        "cases": [
            {
                "id": "example",
                "arms": {
                    "no_skill_no_mcp": {
                        "trials": [
                            {"trial": 1, "status": "ok", "answer": "42"},
                            {"trial": 2, "status": "error", "answer": ""},
                            {"trial": 4, "status": "ok", "answer": "ignored"},
                        ]
                    },
                    "skill_mcp": {"trials": [{"trial": 1, "status": "ok", "answer": "42"}]},
                },
            }
        ],
    }

    completed = _completed_trial_results(
        report,
        case_ids={"example"},
        model="gpt-5.5",
        reasoning_effort="xhigh",
        trials_per_arm=3,
    )

    assert completed == {
        ("example", "no_skill_no_mcp", 1): {
            "trial": 1,
            "status": "ok",
            "answer": "42",
        },
        ("example", "skill_mcp", 1): {
            "trial": 1,
            "status": "ok",
            "answer": "42",
        },
    }


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
