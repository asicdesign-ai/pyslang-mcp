"""Shared internal types for pyslang-mcp."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]


@dataclass(frozen=True, slots=True)
class ProjectConfig:
    """Normalized, read-only project configuration."""

    project_root: Path
    files: tuple[Path, ...]
    include_dirs: tuple[Path, ...]
    defines: tuple[tuple[str, str | None], ...]
    top_modules: tuple[str, ...]
    filelists: tuple[Path, ...] = ()
    source: Literal["files", "filelist"] = "files"
    primary_input: Path | None = None
    unsupported_filelist_entries: tuple[str, ...] = ()

    def defines_dict(self) -> dict[str, str | None]:
        return dict(self.defines)


@dataclass(slots=True)
class AnalysisBundle:
    """Fully prepared pyslang analysis state."""

    project: ProjectConfig
    source_manager: Any
    bag: Any
    compilation: Any
    syntax_trees: dict[Path, Any]
    diagnostic_engine: Any
    tracked_paths: tuple[Path, ...]
