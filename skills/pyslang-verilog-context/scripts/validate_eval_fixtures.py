#!/usr/bin/env python3
"""Validate pyslang-verilog-context eval manifest paths."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


HDL_SUFFIXES = {".sv", ".svh", ".v", ".vh", ".f"}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def validate(manifest_path: Path) -> list[str]:
    errors: list[str] = []
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    evals_dir = manifest_path.parent

    if manifest.get("skill") != "pyslang-verilog-context":
        errors.append("manifest skill must be pyslang-verilog-context")

    for source in _as_list(manifest.get("fixture_sources")):
        copied_to = source.get("copied_to")
        if not isinstance(copied_to, str):
            errors.append("fixture source missing copied_to")
            continue
        source_dir = evals_dir / copied_to
        if not source_dir.is_dir():
            errors.append(f"fixture source directory missing: {copied_to}")
            continue
        if not any(path.suffix in HDL_SUFFIXES for path in source_dir.rglob("*")):
            errors.append(f"fixture source has no HDL/filelist files: {copied_to}")

    for case in _as_list(manifest.get("cases")):
        case_id = case.get("id", "<missing-id>")
        prompt = case.get("prompt")
        fixture_root = case.get("fixture_root")
        case_input = case.get("input", {})

        if not isinstance(prompt, str) or not (evals_dir / prompt).is_file():
            errors.append(f"{case_id}: prompt missing: {prompt}")

        if not isinstance(fixture_root, str):
            errors.append(f"{case_id}: fixture_root missing")
            continue

        root = evals_dir / fixture_root
        if not root.exists():
            errors.append(f"{case_id}: fixture_root not found: {fixture_root}")
            continue

        if not isinstance(case_input, dict):
            errors.append(f"{case_id}: input must be an object")
            continue

        for rel in _as_list(case_input.get("files")):
            if not isinstance(rel, str) or not (root / rel).is_file():
                errors.append(f"{case_id}: input file missing: {fixture_root}/{rel}")

        filelist = case_input.get("filelist")
        if filelist is not None and (
            not isinstance(filelist, str) or not (root / filelist).is_file()
        ):
            errors.append(f"{case_id}: filelist missing: {fixture_root}/{filelist}")

        if not _as_list(case.get("expected_tool_evidence")):
            errors.append(f"{case_id}: expected_tool_evidence must not be empty")
        if not _as_list(case.get("pass_criteria")):
            errors.append(f"{case_id}: pass_criteria must not be empty")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "manifest",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "evals" / "manifest.json",
    )
    args = parser.parse_args()

    errors = validate(args.manifest)
    if errors:
        for error in errors:
            print(error)
        return 1

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    print(
        f"ok: {len(manifest.get('cases', []))} cases, "
        f"{len(manifest.get('fixture_sources', []))} fixture sources"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
