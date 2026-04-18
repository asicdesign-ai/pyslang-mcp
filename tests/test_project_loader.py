from __future__ import annotations

from pathlib import Path

import pytest

from pyslang_mcp.project_loader import (
    PathOutsideRootError,
    load_project_from_filelist,
    load_project_from_files,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_load_project_from_filelist_expands_files_and_defines() -> None:
    project_root = FIXTURES / "multi_file"
    config = load_project_from_filelist(
        project_root=project_root,
        filelist="project.f",
    )

    assert config.source == "filelist"
    assert [path.name for path in config.files] == ["pkg.sv", "child.sv", "top.sv"]
    assert dict(config.defines) == {"WIDTH": "8"}
    assert [path.name for path in config.include_dirs] == ["include"]
    assert config.filelists[-1].name == "rtl.f"


def test_load_project_from_files_rejects_paths_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside.sv"
    root.mkdir()
    outside.write_text("module bad; endmodule\n", encoding="utf-8")

    with pytest.raises(PathOutsideRootError):
        load_project_from_files(
            project_root=root,
            files=[str(outside)],
        )
