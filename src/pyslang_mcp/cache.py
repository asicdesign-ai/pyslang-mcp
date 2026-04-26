"""In-memory project analysis cache keyed by config plus tracked mtimes."""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any

from .serializers import project_config_json
from .types import AnalysisBundle, ProjectConfig


@dataclass(slots=True)
class _CacheEntry:
    project_hash: str
    mtimes: tuple[tuple[str, int], ...]
    bundle: AnalysisBundle
    tool_results: OrderedDict[str, dict[str, Any]]


class AnalysisCache:
    """Bounded process-local analysis cache."""

    def __init__(self, *, max_entries: int = 16, max_tool_results_per_entry: int = 64) -> None:
        self._entries: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._lock = RLock()
        self._max_entries = max(1, max_entries)
        self._max_tool_results_per_entry = max(1, max_tool_results_per_entry)

    def get_or_build(
        self,
        project: ProjectConfig,
        factory: Callable[[], AnalysisBundle],
    ) -> AnalysisBundle:
        """Return a cached analysis bundle when tracked inputs have not changed."""

        cache_key = self._project_hash(project)
        with self._lock:
            entry = self._entries.get(cache_key)
            if entry is not None:
                if entry.mtimes == self._snapshot_mtimes(entry.bundle.tracked_paths):
                    self._entries.move_to_end(cache_key)
                    return entry.bundle
                self._entries.pop(cache_key, None)

        bundle = factory()
        new_entry = _CacheEntry(
            project_hash=cache_key,
            mtimes=self._snapshot_mtimes(bundle.tracked_paths),
            bundle=bundle,
            tool_results=OrderedDict(),
        )
        with self._lock:
            self._entries[cache_key] = new_entry
            self._entries.move_to_end(cache_key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)
        return bundle

    def get_or_compute_tool_result(
        self,
        project: ProjectConfig,
        *,
        tool_name: str,
        tool_args: dict[str, object] | None,
        bundle_factory: Callable[[], AnalysisBundle],
        result_factory: Callable[[AnalysisBundle], dict[str, Any]],
    ) -> dict[str, Any]:
        """Return a cached tool result for a live project bundle when available."""

        bundle = self.get_or_build(project, bundle_factory)
        cache_key = project_hash(project)
        tool_cache_key = self._tool_cache_key(tool_name, tool_args)

        with self._lock:
            entry = self._entries.get(cache_key)
            if (
                entry is not None
                and entry.bundle is bundle
                and entry.mtimes == self._snapshot_mtimes(entry.bundle.tracked_paths)
            ):
                cached = entry.tool_results.get(tool_cache_key)
                if cached is not None:
                    entry.tool_results.move_to_end(tool_cache_key)
                    self._entries.move_to_end(cache_key)
                    return cached

        result = result_factory(bundle)
        with self._lock:
            entry = self._entries.get(cache_key)
            if (
                entry is not None
                and entry.bundle is bundle
                and entry.mtimes == self._snapshot_mtimes(entry.bundle.tracked_paths)
            ):
                entry.tool_results[tool_cache_key] = result
                entry.tool_results.move_to_end(tool_cache_key)
                while len(entry.tool_results) > self._max_tool_results_per_entry:
                    entry.tool_results.popitem(last=False)
                self._entries.move_to_end(cache_key)
        return result

    def clear(self) -> None:
        """Drop all cached entries."""

        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        """Return the number of live cache entries."""

        with self._lock:
            return len(self._entries)

    def _project_hash(self, project: ProjectConfig) -> str:
        return project_hash(project)

    def _tool_cache_key(self, tool_name: str, tool_args: dict[str, object] | None) -> str:
        payload = json.dumps(
            {
                "tool_name": tool_name,
                "tool_args": tool_args or {},
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def _snapshot_mtimes(self, paths: tuple[Path, ...]) -> tuple[tuple[str, int], ...]:
        mtimes: list[tuple[str, int]] = []
        for path in sorted(paths):
            mtime_ns = path.stat().st_mtime_ns if path.exists() else -1
            mtimes.append((path.as_posix(), mtime_ns))
        return tuple(mtimes)


def project_hash(project: ProjectConfig) -> str:
    """Return the stable cache hash for a normalized project config."""

    payload = json.dumps(project_config_json(project), sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


DEFAULT_CACHE = AnalysisCache(max_entries=16)
