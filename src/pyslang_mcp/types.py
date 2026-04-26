"""Shared internal types for pyslang-mcp."""

from __future__ import annotations

from dataclasses import dataclass, field
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
class IndexedDeclaration:
    """Precomputed declaration lookup entry."""

    candidates: tuple[str, ...]
    output: dict[str, Any]


@dataclass(slots=True)
class IndexedReference:
    """Precomputed reference lookup entry."""

    candidates: tuple[str, ...]
    output: dict[str, Any]


@dataclass(slots=True)
class AnalysisIndex:
    """Warm-query index derived from a compiled project."""

    design_units: tuple[Any, ...]
    design_unit_records: tuple[dict[str, Any], ...]
    design_unit_symbols_by_key: dict[tuple[str, str], Any]
    instances: tuple[Any, ...]
    instance_records_by_path: dict[str, dict[str, Any]]
    children_by_parent: dict[str | None, tuple[str, ...]]
    top_instance_paths: tuple[str, ...]
    declarations: tuple[IndexedDeclaration, ...]
    references: tuple[IndexedReference, ...]
    design_unit_description_cache: dict[str, dict[str, Any]] = field(default_factory=dict)


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
    index: AnalysisIndex | None = None
