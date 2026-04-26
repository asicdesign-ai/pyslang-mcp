from __future__ import annotations

import textwrap
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


def test_filelist_strips_inline_comments_without_whitespace(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (root / "top.sv").write_text("module top; endmodule\n", encoding="utf-8")
    (root / "project.f").write_text("top.sv// keep comment out of the path\n", encoding="utf-8")

    config = load_project_from_filelist(project_root=root, filelist="project.f")

    assert [path.name for path in config.files] == ["top.sv"]


def test_filelist_reports_unsupported_library_tokens(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (root / "lib").mkdir()
    (root / "top.sv").write_text("module top; endmodule\n", encoding="utf-8")
    (root / "vendor.sv").write_text("module vendor; endmodule\n", encoding="utf-8")
    (root / "project.f").write_text(
        textwrap.dedent(
            """\
            -y lib
            +libext+
            +libext+.sv+.v
            -v vendor.sv
            top.sv
            """
        ),
        encoding="utf-8",
    )

    config = load_project_from_filelist(project_root=root, filelist="project.f")

    assert [path.name for path in config.files] == ["top.sv"]
    assert list(config.unsupported_filelist_entries) == [
        "project.f:1:-y",
        "project.f:1:lib",
        "project.f:2:+libext+",
        "project.f:3:+libext+.sv+.v",
        "project.f:4:-v",
        "project.f:4:vendor.sv",
    ]


def test_filelist_supports_common_define_and_include_forms(tmp_path: Path) -> None:
    root = tmp_path / "project"
    compile_dir = root / "compile"
    rtl_dir = root / "rtl"
    include_dir = root / "include"
    extra_include_dir = root / "extra_include"
    compile_dir.mkdir(parents=True)
    rtl_dir.mkdir()
    include_dir.mkdir()
    extra_include_dir.mkdir()
    (rtl_dir / "top.sv").write_text("module top; endmodule\n", encoding="utf-8")
    (compile_dir / "project.f").write_text(
        textwrap.dedent(
            """\
            -I../include
            -I ../extra_include
            +incdir+../include+../extra_include
            -DDEBUG
            -D WIDTH=16
            -DDEPTH=4
            +define+FLAG+MODE=2
            -sv
            -timescale 1ns/1ps
            ../rtl/top.sv
            """
        ),
        encoding="utf-8",
    )

    config = load_project_from_filelist(project_root=root, filelist="compile/project.f")

    assert [path.relative_to(root).as_posix() for path in config.include_dirs] == [
        "include",
        "extra_include",
    ]
    assert dict(config.defines) == {
        "DEBUG": None,
        "DEPTH": "4",
        "FLAG": None,
        "MODE": "2",
        "WIDTH": "16",
    }
    assert [path.relative_to(root).as_posix() for path in config.files] == ["rtl/top.sv"]
    assert list(config.unsupported_filelist_entries) == [
        "project.f:8:-sv",
        "project.f:9:-timescale",
        "project.f:9:1ns/1ps",
    ]
