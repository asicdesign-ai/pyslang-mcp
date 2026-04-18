"""In-memory project analysis cache keyed by config plus tracked mtimes."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import RLock

from .serializers import project_config_json
from .types import AnalysisBundle, ProjectConfig


@dataclass(slots=True)
class _CacheEntry:
    project_hash: str
    mtimes: tuple[tuple[str, int], ...]
    bundle: AnalysisBundle


class AnalysisCache:
    """Simple process-local analysis cache."""

    def __init__(self) -> None:
        self._entries: dict[str, _CacheEntry] = {}
        self._lock = RLock()

    def get_or_build(
        self,
        project: ProjectConfig,
        factory: Callable[[], AnalysisBundle],
    ) -> AnalysisBundle:
        """Return a cached analysis bundle when tracked inputs have not changed."""

        cache_key = self._project_hash(project)
        with self._lock:
            entry = self._entries.get(cache_key)
            if entry is not None and entry.mtimes == self._snapshot_mtimes(
                entry.bundle.tracked_paths
            ):
                return entry.bundle

        bundle = factory()
        new_entry = _CacheEntry(
            project_hash=cache_key,
            mtimes=self._snapshot_mtimes(bundle.tracked_paths),
            bundle=bundle,
        )
        with self._lock:
            self._entries[cache_key] = new_entry
        return bundle

    def clear(self) -> None:
        """Drop all cached entries."""

        with self._lock:
            self._entries.clear()

    def _project_hash(self, project: ProjectConfig) -> str:
        payload = json.dumps(project_config_json(project), sort_keys=True).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def _snapshot_mtimes(self, paths: tuple[Path, ...]) -> tuple[tuple[str, int], ...]:
        mtimes: list[tuple[str, int]] = []
        for path in sorted(paths):
            mtime_ns = path.stat().st_mtime_ns if path.exists() else -1
            mtimes.append((path.as_posix(), mtime_ns))
        return tuple(mtimes)


DEFAULT_CACHE = AnalysisCache()
