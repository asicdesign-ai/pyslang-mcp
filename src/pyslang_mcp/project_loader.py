"""Project loading, root safety checks, and `.f` parsing."""

from __future__ import annotations

import re
import shlex
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from .types import ProjectConfig


class ProjectLoadError(ValueError):
    """Base project loading error."""


class PathOutsideRootError(ProjectLoadError):
    """Raised when a requested path escapes the declared project root."""


def resolve_project_root(project_root: str | Path) -> Path:
    """Normalize and validate the declared project root."""

    root = Path(project_root).expanduser().resolve()
    if not root.exists():
        raise ProjectLoadError(f"Project root does not exist: {root}")
    if not root.is_dir():
        raise ProjectLoadError(f"Project root is not a directory: {root}")
    return root


def load_project_from_files(
    *,
    project_root: str | Path,
    files: Iterable[str],
    include_dirs: Iterable[str] | None = None,
    defines: dict[str, str | None] | None = None,
    top_modules: Iterable[str] | None = None,
) -> ProjectConfig:
    """Build a normalized project config from an explicit file list."""

    root = resolve_project_root(project_root)
    normalized_files = tuple(
        _dedupe_paths(
            _normalize_path(root, file_path, kind="source file", base_dir=root, must_exist=True)
            for file_path in files
        )
    )
    if not normalized_files:
        raise ProjectLoadError("At least one source file is required.")
    normalized_include_dirs = tuple(
        _dedupe_paths(
            _normalize_path(
                root,
                include_dir,
                kind="include directory",
                base_dir=root,
                must_exist=True,
                expect_dir=True,
            )
            for include_dir in include_dirs or ()
        )
    )
    return ProjectConfig(
        project_root=root,
        files=normalized_files,
        include_dirs=normalized_include_dirs,
        defines=_normalize_defines(defines),
        top_modules=_normalize_top_modules(top_modules),
        source="files",
    )


def load_project_from_filelist(
    *,
    project_root: str | Path,
    filelist: str | Path,
    include_dirs: Iterable[str] | None = None,
    defines: dict[str, str | None] | None = None,
    top_modules: Iterable[str] | None = None,
) -> ProjectConfig:
    """Build a normalized project config from a filelist."""

    root = resolve_project_root(project_root)
    normalized_filelist = _normalize_path(
        root,
        filelist,
        kind="filelist",
        base_dir=root,
        must_exist=True,
    )
    parsed = _parse_filelist(root=root, filelist=normalized_filelist)
    merged_defines = dict(parsed.defines)
    merged_defines.update(defines or {})
    all_include_dirs = [*parsed.include_dirs, *(include_dirs or [])]
    normalized_include_dirs = tuple(
        _dedupe_paths(
            _normalize_path(
                root,
                include_dir,
                kind="include directory",
                base_dir=root,
                must_exist=True,
                expect_dir=True,
            )
            for include_dir in all_include_dirs
        )
    )
    if not parsed.files:
        raise ProjectLoadError(f"Filelist resolved no source files: {normalized_filelist}")
    return ProjectConfig(
        project_root=root,
        files=tuple(_dedupe_paths(parsed.files)),
        include_dirs=normalized_include_dirs,
        defines=_normalize_defines(merged_defines),
        top_modules=_normalize_top_modules(top_modules),
        filelists=tuple(_dedupe_paths(parsed.filelists)),
        source="filelist",
        primary_input=normalized_filelist,
        unsupported_filelist_entries=tuple(parsed.unsupported_entries),
    )


@dataclass(slots=True)
class _ParsedFilelist:
    files: list[Path] = field(default_factory=list)
    include_dirs: list[str] = field(default_factory=list)
    defines: dict[str, str | None] = field(default_factory=dict)
    filelists: list[Path] = field(default_factory=list)
    unsupported_entries: list[str] = field(default_factory=list)
    seen: set[Path] = field(default_factory=set)


def _parse_filelist(*, root: Path, filelist: Path) -> _ParsedFilelist:
    state = _ParsedFilelist()
    _visit_filelist(root=root, filelist=filelist, state=state)
    return state


def _visit_filelist(*, root: Path, filelist: Path, state: _ParsedFilelist) -> None:
    if filelist in state.seen:
        return
    state.seen.add(filelist)
    state.filelists.append(filelist)

    for line_number, raw_line in enumerate(
        filelist.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("//") or line.startswith("#"):
            continue
        line = re.split(r"\s+//", raw_line, maxsplit=1)[0]
        line = re.split(r"\s+#", line, maxsplit=1)[0]
        tokens = shlex.split(line, comments=False, posix=True)
        index = 0
        while index < len(tokens):
            token = tokens[index]

            if token in {"-f", "-F"}:
                index += 1
                if index >= len(tokens):
                    raise ProjectLoadError(
                        f"Missing nested filelist after {token} in {filelist}:{line_number}"
                    )
                nested = _normalize_path(
                    root,
                    tokens[index],
                    kind="nested filelist",
                    base_dir=filelist.parent,
                    must_exist=True,
                )
                _visit_filelist(root=root, filelist=nested, state=state)
            elif token.startswith("-f") and len(token) > 2:
                nested = _normalize_path(
                    root,
                    token[2:],
                    kind="nested filelist",
                    base_dir=filelist.parent,
                    must_exist=True,
                )
                _visit_filelist(root=root, filelist=nested, state=state)
            elif token.startswith("-F") and len(token) > 2:
                nested = _normalize_path(
                    root,
                    token[2:],
                    kind="nested filelist",
                    base_dir=filelist.parent,
                    must_exist=True,
                )
                _visit_filelist(root=root, filelist=nested, state=state)
            elif token == "-I":
                index += 1
                if index >= len(tokens):
                    raise ProjectLoadError(
                        f"Missing include dir after -I in {filelist}:{line_number}"
                    )
                state.include_dirs.append(tokens[index])
            elif token.startswith("+incdir+"):
                raw_dirs = [entry for entry in token[len("+incdir+") :].split("+") if entry]
                state.include_dirs.extend(raw_dirs)
            elif token.startswith("+define+"):
                raw_defines = [entry for entry in token[len("+define+") :].split("+") if entry]
                for entry in raw_defines:
                    key, value = _parse_define(entry)
                    state.defines[key] = value
            elif token in {"-y", "+libext+", "-v"} or token.startswith("+libext+"):
                state.unsupported_entries.append(f"{filelist.name}:{line_number}:{token}")
                if token in {"-y", "-v"} and index + 1 < len(tokens):
                    index += 1
                    state.unsupported_entries.append(
                        f"{filelist.name}:{line_number}:{tokens[index]}"
                    )
            else:
                state.files.append(
                    _normalize_path(
                        root,
                        token,
                        kind="source file",
                        base_dir=filelist.parent,
                        must_exist=True,
                    )
                )
            index += 1


def _normalize_path(
    root: Path,
    raw_path: str | Path,
    *,
    kind: str,
    base_dir: Path,
    must_exist: bool,
    expect_dir: bool = False,
) -> Path:
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    candidate = candidate.resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise PathOutsideRootError(f"{kind.capitalize()} escapes project root: {raw_path}") from exc
    if must_exist and not candidate.exists():
        raise ProjectLoadError(f"{kind.capitalize()} does not exist: {candidate}")
    if expect_dir and candidate.exists() and not candidate.is_dir():
        raise ProjectLoadError(f"{kind.capitalize()} is not a directory: {candidate}")
    if not expect_dir and candidate.exists() and not candidate.is_file():
        raise ProjectLoadError(f"{kind.capitalize()} is not a file: {candidate}")
    return candidate


def _dedupe_paths(paths: Iterable[Path]) -> list[Path]:
    ordered: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        if path not in seen:
            ordered.append(path)
            seen.add(path)
    return ordered


def _normalize_defines(defines: dict[str, str | None] | None) -> tuple[tuple[str, str | None], ...]:
    if not defines:
        return ()
    normalized: list[tuple[str, str | None]] = []
    for key, value in sorted(defines.items()):
        if not key or not key.strip():
            raise ProjectLoadError("Define names must be non-empty.")
        normalized.append((key.strip(), value.strip() if isinstance(value, str) else value))
    return tuple(normalized)


def _normalize_top_modules(top_modules: Iterable[str] | None) -> tuple[str, ...]:
    if not top_modules:
        return ()
    ordered: list[str] = []
    seen: set[str] = set()
    for raw_name in top_modules:
        name = raw_name.strip()
        if not name:
            raise ProjectLoadError("Top module names must be non-empty.")
        if name not in seen:
            ordered.append(name)
            seen.add(name)
    return tuple(ordered)


def _parse_define(raw_define: str) -> tuple[str, str | None]:
    if "=" in raw_define:
        key, value = raw_define.split("=", 1)
        return key.strip(), value.strip()
    return raw_define.strip(), None
