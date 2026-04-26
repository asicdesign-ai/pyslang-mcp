from __future__ import annotations

from pathlib import Path
from typing import cast

from pyslang_mcp.cache import AnalysisCache
from pyslang_mcp.types import AnalysisBundle, ProjectConfig


def _project(tmp_path: Path, name: str) -> ProjectConfig:
    file_path = tmp_path / f"{name}.sv"
    file_path.write_text(f"module {name}; endmodule\n", encoding="utf-8")
    return ProjectConfig(
        project_root=tmp_path,
        files=(file_path,),
        include_dirs=(),
        defines=(),
        top_modules=(),
    )


def test_analysis_cache_evicts_oldest_entry(tmp_path: Path) -> None:
    cache = AnalysisCache(max_entries=1)
    first = _project(tmp_path, "first")
    second = _project(tmp_path, "second")
    builds: list[str] = []

    def factory(project: ProjectConfig) -> AnalysisBundle:
        builds.append(project.files[0].name)
        return cast(AnalysisBundle, type("Bundle", (), {"tracked_paths": project.files})())

    cache.get_or_build(first, lambda: factory(first))
    cache.get_or_build(second, lambda: factory(second))
    cache.get_or_build(first, lambda: factory(first))

    assert len(cache) == 1
    assert builds == ["first.sv", "second.sv", "first.sv"]


def test_tool_result_cache_reuses_identical_tool_args(tmp_path: Path) -> None:
    cache = AnalysisCache(max_entries=1)
    project = _project(tmp_path, "top")
    bundle_builds = 0
    result_calls = 0

    def bundle_factory() -> AnalysisBundle:
        nonlocal bundle_builds
        bundle_builds += 1
        return cast(AnalysisBundle, type("Bundle", (), {"tracked_paths": project.files})())

    def result_factory(_bundle: AnalysisBundle) -> dict[str, object]:
        nonlocal result_calls
        result_calls += 1
        return {"call_count": result_calls}

    first = cache.get_or_compute_tool_result(
        project,
        tool_name="find_symbol",
        tool_args={"query": "payload", "match_mode": "exact"},
        bundle_factory=bundle_factory,
        result_factory=result_factory,
    )
    second = cache.get_or_compute_tool_result(
        project,
        tool_name="find_symbol",
        tool_args={"query": "payload", "match_mode": "exact"},
        bundle_factory=bundle_factory,
        result_factory=result_factory,
    )
    third = cache.get_or_compute_tool_result(
        project,
        tool_name="find_symbol",
        tool_args={"query": "payload", "match_mode": "contains"},
        bundle_factory=bundle_factory,
        result_factory=result_factory,
    )

    assert first == {"call_count": 1}
    assert second == {"call_count": 1}
    assert third == {"call_count": 2}
    assert bundle_builds == 1
    assert result_calls == 2
