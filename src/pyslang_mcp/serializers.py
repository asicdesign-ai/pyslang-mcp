"""JSON serialization helpers and truncation utilities."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import TypeVar, cast

from .types import ProjectConfig

T = TypeVar("T")


def relative_path(root: Path, path: Path) -> str:
    """Return a stable, compact project-relative path when possible."""

    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def limit_list(items: Sequence[object], max_items: int) -> tuple[list[object], dict[str, object]]:
    """Apply a stable item limit and expose truncation metadata."""

    total = len(items)
    limited = list(items[: max(max_items, 0)])
    return limited, {
        "returned": len(limited),
        "total": total,
        "truncated": total > len(limited),
        "remaining": max(total - len(limited), 0),
    }


def top_counts(counter: Counter[str], max_items: int) -> dict[str, int]:
    """Return a stable mapping of the most common counter entries."""

    pairs = sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:max_items]
    return {key: value for key, value in pairs}


def project_config_json(config: ProjectConfig) -> dict[str, object]:
    """Serialize project config to stable JSON."""

    return {
        "project_root": config.project_root.as_posix(),
        "source": config.source,
        "primary_input": config.primary_input.as_posix() if config.primary_input else None,
        "files": [relative_path(config.project_root, path) for path in config.files],
        "include_dirs": [relative_path(config.project_root, path) for path in config.include_dirs],
        "defines": {key: value for key, value in config.defines},
        "top_modules": list(config.top_modules),
        "filelists": [relative_path(config.project_root, path) for path in config.filelists],
        "unsupported_filelist_entries": list(config.unsupported_filelist_entries),
    }


def stabilize_json(value: T) -> T:
    """Normalize recursively into a stable JSON ordering."""

    return cast(T, json.loads(json.dumps(value, sort_keys=True)))


def ensure_jsonable_paths(paths: Iterable[Path], root: Path) -> list[str]:
    """Serialize paths relative to the project root."""

    return [relative_path(root, path) for path in paths]
