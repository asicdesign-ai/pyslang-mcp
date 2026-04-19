# ruff: noqa: E402

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
CORPUS_PATH = REPO_ROOT / "examples" / "hdl" / "corpus.json"
HDL_SUFFIXES = {".sv", ".svh", ".v"}

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from pyslang_mcp.analysis import build_analysis, get_diagnostics
from pyslang_mcp.project_loader import load_project_from_filelist, load_project_from_files


def load_examples(*, smoke_only: bool = False) -> list[dict[str, Any]]:
    payload = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    examples = list(payload["examples"])
    if smoke_only:
        return [example for example in examples if example.get("ci_smoke")]
    return examples


def resolve_example_root(example: dict[str, Any]) -> Path:
    return REPO_ROOT / str(example["project_root"])


def validate_manifest_roots(examples: list[dict[str, Any]]) -> None:
    missing_roots = [
        str(resolve_example_root(example))
        for example in examples
        if not resolve_example_root(example).is_dir()
    ]
    if missing_roots:
        joined = "\n".join(sorted(missing_roots))
        raise AssertionError(f"Manifest project roots do not exist:\n{joined}")


def validate_manifest_file_coverage(examples: list[dict[str, Any]]) -> None:
    known_roots = {resolve_example_root(example) for example in examples}
    known_files: set[Path] = set()
    for root in known_roots:
        known_files.update(
            path for path in root.rglob("*") if path.is_file() and path.suffix in HDL_SUFFIXES
        )

    corpus_root = REPO_ROOT / "examples" / "hdl"
    actual_files = {
        path for path in corpus_root.rglob("*") if path.is_file() and path.suffix in HDL_SUFFIXES
    }
    missing = sorted(actual_files - known_files)
    if missing:
        joined = "\n".join(path.relative_to(REPO_ROOT).as_posix() for path in missing)
        raise AssertionError(f"HDL files outside manifest coverage:\n{joined}")


def load_project(example: dict[str, Any]):
    project_root = resolve_example_root(example)
    top_modules = example.get("top_modules")
    if "filelist" in example:
        return load_project_from_filelist(
            project_root=project_root,
            filelist=str(example["filelist"]),
            top_modules=top_modules,
        )
    return load_project_from_files(
        project_root=project_root,
        files=list(example["files"]),
        top_modules=top_modules,
    )


def validate_with_pyslang(example: dict[str, Any]) -> None:
    project = load_project(example)
    bundle = build_analysis(project)
    diagnostics = get_diagnostics(bundle)
    if diagnostics["summary"]["total"] != 0:
        payload = json.dumps(diagnostics, indent=2, sort_keys=True)
        raise AssertionError(f"pyslang diagnostics found for {example['id']}:\n{payload}")


def validate_with_verilator(example: dict[str, Any]) -> None:
    project = load_project(example)
    command = ["verilator", "--lint-only"]
    top_modules = list(project.top_modules)
    if len(top_modules) == 1:
        command.extend(["--top-module", top_modules[0]])
    for include_dir in project.include_dirs:
        command.append(f"-I{include_dir}")
    for key, value in project.defines:
        if value is None:
            command.append(f"+define+{key}")
        else:
            command.append(f"+define+{key}={value}")
    command.extend(str(path) for path in project.files)
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"Verilator failed for {example['id']}:\n"
            f"command: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def validate_example(example: dict[str, Any]) -> None:
    validate_with_pyslang(example)
    validate_with_verilator(example)
