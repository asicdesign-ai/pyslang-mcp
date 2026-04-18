"""FastMCP server wiring for pyslang-mcp."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .analysis import (
    MatchMode,
    build_analysis,
    filelist_summary,
    parse_summary,
)
from .analysis import (
    describe_design_unit as describe_design_unit_core,
)
from .analysis import (
    dump_syntax_tree_summary as dump_syntax_tree_summary_core,
)
from .analysis import (
    find_symbol as find_symbol_core,
)
from .analysis import (
    get_diagnostics as get_diagnostics_core,
)
from .analysis import (
    get_hierarchy as get_hierarchy_core,
)
from .analysis import (
    get_project_summary as get_project_summary_core,
)
from .analysis import (
    list_design_units as list_design_units_core,
)
from .analysis import (
    preprocess_files as preprocess_files_core,
)
from .cache import DEFAULT_CACHE, AnalysisCache
from .project_loader import load_project_from_filelist, load_project_from_files
from .types import ProjectConfig

READ_ONLY_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


def create_server(cache: AnalysisCache | None = None) -> FastMCP:
    """Create the MCP server instance."""

    analysis_cache = cache or DEFAULT_CACHE
    mcp = FastMCP("pyslang_mcp")

    def resolve_project(
        *,
        project_root: str,
        files: list[str] | None = None,
        filelist: str | None = None,
        include_dirs: list[str] | None = None,
        defines: dict[str, str | None] | None = None,
        top_modules: list[str] | None = None,
    ) -> ProjectConfig:
        if bool(files) == bool(filelist):
            raise ValueError("Provide exactly one of `files` or `filelist`.")
        if files:
            return load_project_from_files(
                project_root=project_root,
                files=files,
                include_dirs=include_dirs,
                defines=defines,
                top_modules=top_modules,
            )
        return load_project_from_filelist(
            project_root=project_root,
            filelist=filelist or "",
            include_dirs=include_dirs,
            defines=defines,
            top_modules=top_modules,
        )

    def analyze(project: ProjectConfig) -> Any:
        return analysis_cache.get_or_build(project, lambda: build_analysis(project))

    @mcp.tool(
        name="parse_files",
        annotations=READ_ONLY_ANNOTATIONS,
        description=(
            "Parse and elaborate an explicit list of Verilog/SystemVerilog files "
            "under a declared project root."
        ),
    )
    def parse_files(
        project_root: str,
        files: list[str],
        include_dirs: list[str] | None = None,
        defines: dict[str, str | None] | None = None,
        top_modules: list[str] | None = None,
    ) -> dict[str, Any]:
        bundle = analyze(
            load_project_from_files(
                project_root=project_root,
                files=files,
                include_dirs=include_dirs,
                defines=defines,
                top_modules=top_modules,
            )
        )
        return parse_summary(bundle)

    @mcp.tool(
        name="parse_filelist",
        annotations=READ_ONLY_ANNOTATIONS,
        description=(
            "Parse a project filelist under a declared project root and return "
            "normalized file expansion details."
        ),
    )
    def parse_filelist(
        project_root: str,
        filelist: str,
        include_dirs: list[str] | None = None,
        defines: dict[str, str | None] | None = None,
        top_modules: list[str] | None = None,
    ) -> dict[str, Any]:
        bundle = analyze(
            load_project_from_filelist(
                project_root=project_root,
                filelist=filelist,
                include_dirs=include_dirs,
                defines=defines,
                top_modules=top_modules,
            )
        )
        return filelist_summary(bundle)

    @mcp.tool(
        name="get_diagnostics",
        annotations=READ_ONLY_ANNOTATIONS,
        description=(
            "Return compiler diagnostics for a project described by explicit files or a filelist."
        ),
    )
    def get_diagnostics(
        project_root: str,
        files: list[str] | None = None,
        filelist: str | None = None,
        include_dirs: list[str] | None = None,
        defines: dict[str, str | None] | None = None,
        top_modules: list[str] | None = None,
        max_items: int = 200,
    ) -> dict[str, Any]:
        bundle = analyze(
            resolve_project(
                project_root=project_root,
                files=files,
                filelist=filelist,
                include_dirs=include_dirs,
                defines=defines,
                top_modules=top_modules,
            )
        )
        return get_diagnostics_core(bundle, max_items=max_items)

    @mcp.tool(
        name="list_design_units",
        annotations=READ_ONLY_ANNOTATIONS,
        description=(
            "List project-local modules, interfaces, and packages from an analyzed project."
        ),
    )
    def list_design_units(
        project_root: str,
        files: list[str] | None = None,
        filelist: str | None = None,
        include_dirs: list[str] | None = None,
        defines: dict[str, str | None] | None = None,
        top_modules: list[str] | None = None,
        max_items: int = 200,
    ) -> dict[str, Any]:
        bundle = analyze(
            resolve_project(
                project_root=project_root,
                files=files,
                filelist=filelist,
                include_dirs=include_dirs,
                defines=defines,
                top_modules=top_modules,
            )
        )
        return list_design_units_core(bundle, max_items=max_items)

    @mcp.tool(
        name="describe_design_unit",
        annotations=READ_ONLY_ANNOTATIONS,
        description="Describe a single design unit by exact name.",
    )
    def describe_design_unit(
        project_root: str,
        name: str,
        files: list[str] | None = None,
        filelist: str | None = None,
        include_dirs: list[str] | None = None,
        defines: dict[str, str | None] | None = None,
        top_modules: list[str] | None = None,
    ) -> dict[str, Any]:
        bundle = analyze(
            resolve_project(
                project_root=project_root,
                files=files,
                filelist=filelist,
                include_dirs=include_dirs,
                defines=defines,
                top_modules=top_modules,
            )
        )
        return describe_design_unit_core(bundle, name=name)

    @mcp.tool(
        name="get_hierarchy",
        annotations=READ_ONLY_ANNOTATIONS,
        description="Return the elaborated instance hierarchy for the analyzed project.",
    )
    def get_hierarchy(
        project_root: str,
        files: list[str] | None = None,
        filelist: str | None = None,
        include_dirs: list[str] | None = None,
        defines: dict[str, str | None] | None = None,
        top_modules: list[str] | None = None,
        max_depth: int = 8,
        max_children: int = 100,
    ) -> dict[str, Any]:
        bundle = analyze(
            resolve_project(
                project_root=project_root,
                files=files,
                filelist=filelist,
                include_dirs=include_dirs,
                defines=defines,
                top_modules=top_modules,
            )
        )
        return get_hierarchy_core(bundle, max_depth=max_depth, max_children=max_children)

    @mcp.tool(
        name="find_symbol",
        annotations=READ_ONLY_ANNOTATIONS,
        description="Search declarations and references by symbol name or hierarchical path.",
    )
    def find_symbol(
        project_root: str,
        query: str,
        files: list[str] | None = None,
        filelist: str | None = None,
        include_dirs: list[str] | None = None,
        defines: dict[str, str | None] | None = None,
        top_modules: list[str] | None = None,
        match_mode: MatchMode = "exact",
        include_references: bool = True,
        max_results: int = 100,
    ) -> dict[str, Any]:
        bundle = analyze(
            resolve_project(
                project_root=project_root,
                files=files,
                filelist=filelist,
                include_dirs=include_dirs,
                defines=defines,
                top_modules=top_modules,
            )
        )
        return find_symbol_core(
            bundle,
            query=query,
            match_mode=match_mode,
            include_references=include_references,
            max_results=max_results,
        )

    @mcp.tool(
        name="dump_syntax_tree_summary",
        annotations=READ_ONLY_ANNOTATIONS,
        description="Summarize syntax tree shapes per file without dumping full raw ASTs.",
    )
    def dump_syntax_tree_summary(
        project_root: str,
        files: list[str] | None = None,
        filelist: str | None = None,
        include_dirs: list[str] | None = None,
        defines: dict[str, str | None] | None = None,
        top_modules: list[str] | None = None,
        max_files: int = 50,
        max_node_kinds: int = 40,
    ) -> dict[str, Any]:
        bundle = analyze(
            resolve_project(
                project_root=project_root,
                files=files,
                filelist=filelist,
                include_dirs=include_dirs,
                defines=defines,
                top_modules=top_modules,
            )
        )
        return dump_syntax_tree_summary_core(
            bundle,
            max_files=max_files,
            max_node_kinds=max_node_kinds,
        )

    @mcp.tool(
        name="preprocess_files",
        annotations=READ_ONLY_ANNOTATIONS,
        description=(
            "Return conservative preprocessing metadata and source excerpts for analyzed files."
        ),
    )
    def preprocess_files(
        project_root: str,
        files: list[str] | None = None,
        filelist: str | None = None,
        include_dirs: list[str] | None = None,
        defines: dict[str, str | None] | None = None,
        top_modules: list[str] | None = None,
        max_files: int = 50,
        max_excerpt_lines: int = 12,
    ) -> dict[str, Any]:
        bundle = analyze(
            resolve_project(
                project_root=project_root,
                files=files,
                filelist=filelist,
                include_dirs=include_dirs,
                defines=defines,
                top_modules=top_modules,
            )
        )
        return preprocess_files_core(
            bundle,
            max_files=max_files,
            max_excerpt_lines=max_excerpt_lines,
        )

    @mcp.tool(
        name="get_project_summary",
        annotations=READ_ONLY_ANNOTATIONS,
        description=(
            "Return a compact summary of files, diagnostics, design units, and top instances."
        ),
    )
    def get_project_summary(
        project_root: str,
        files: list[str] | None = None,
        filelist: str | None = None,
        include_dirs: list[str] | None = None,
        defines: dict[str, str | None] | None = None,
        top_modules: list[str] | None = None,
    ) -> dict[str, Any]:
        bundle = analyze(
            resolve_project(
                project_root=project_root,
                files=files,
                filelist=filelist,
                include_dirs=include_dirs,
                defines=defines,
                top_modules=top_modules,
            )
        )
        return get_project_summary_core(bundle)

    return mcp
