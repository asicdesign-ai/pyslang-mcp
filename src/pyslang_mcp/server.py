"""FastMCP server wiring for pyslang-mcp."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Annotated, Any, TypeVar

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import BaseModel, Field

from .analysis import MatchMode, build_analysis, filelist_summary, parse_summary
from .analysis import describe_design_unit as describe_design_unit_core
from .analysis import dump_syntax_tree_summary as dump_syntax_tree_summary_core
from .analysis import find_symbol as find_symbol_core
from .analysis import get_diagnostics as get_diagnostics_core
from .analysis import get_hierarchy as get_hierarchy_core
from .analysis import get_project_summary as get_project_summary_core
from .analysis import list_design_units as list_design_units_core
from .analysis import preprocess_files as preprocess_files_core
from .cache import DEFAULT_CACHE, AnalysisCache
from .project_loader import (
    PathOutsideRootError,
    ProjectLoadError,
    load_project_from_filelist,
    load_project_from_files,
)
from .schemas import (
    DescribeDesignUnitResult,
    DiagnosticsResult,
    FindSymbolResult,
    HierarchyResult,
    ListDesignUnitsResult,
    ParseFilelistResult,
    ParseFilesResult,
    PreprocessFilesResult,
    ProjectSummaryResult,
    SyntaxTreeSummaryResult,
    ToolErrorDetail,
    ToolErrorResult,
)
from .types import ProjectConfig

READ_ONLY_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
MAX_LIST_ITEMS = 1000
MAX_SYMBOL_RESULTS = 1000
MAX_HIERARCHY_DEPTH = 32
MAX_HIERARCHY_CHILDREN = 1000
MAX_SUMMARY_FILES = 500
MAX_NODE_KINDS = 200
MAX_EXCERPT_LINES = 200

TOOL_NAME_PREFIX = "pyslang_"
PUBLIC_TOOL_NAMES = {
    "parse_files": f"{TOOL_NAME_PREFIX}parse_files",
    "parse_filelist": f"{TOOL_NAME_PREFIX}parse_filelist",
    "get_diagnostics": f"{TOOL_NAME_PREFIX}get_diagnostics",
    "list_design_units": f"{TOOL_NAME_PREFIX}list_design_units",
    "describe_design_unit": f"{TOOL_NAME_PREFIX}describe_design_unit",
    "get_hierarchy": f"{TOOL_NAME_PREFIX}get_hierarchy",
    "find_symbol": f"{TOOL_NAME_PREFIX}find_symbol",
    "dump_syntax_tree_summary": f"{TOOL_NAME_PREFIX}dump_syntax_tree_summary",
    "preprocess_files": f"{TOOL_NAME_PREFIX}preprocess_files",
    "get_project_summary": f"{TOOL_NAME_PREFIX}get_project_summary",
}

ProjectRootArg = Annotated[
    str,
    Field(
        description=(
            "Declared project root. Every source file, filelist, and include directory must "
            "resolve inside this directory or the tool returns an error."
        )
    ),
]
FilesArg = Annotated[
    list[str],
    Field(
        description=(
            "Project-relative or absolute source file paths under `project_root`. Use this for "
            "explicit-file mode instead of `filelist`."
        ),
        min_length=1,
    ),
]
OptionalFilesArg = Annotated[
    list[str] | None,
    Field(
        default=None,
        description=(
            "Project-relative or absolute source file paths under `project_root`. Provide this "
            "or `filelist`, but not both."
        ),
    ),
]
FilelistArg = Annotated[
    str,
    Field(
        description=(
            "Project-relative or absolute filelist path under `project_root`. Supports nested "
            "`-f` / `-F`, `+incdir+`, `-I`, and `+define+` entries."
        )
    ),
]
OptionalFilelistArg = Annotated[
    str | None,
    Field(
        default=None,
        description=(
            "Project-relative or absolute filelist path under `project_root`. Provide this or "
            "`files`, but not both."
        ),
    ),
]
IncludeDirsArg = Annotated[
    list[str] | None,
    Field(
        default=None,
        description=(
            "Additional include directories under `project_root`. These are merged with any "
            "include directories discovered from a filelist."
        ),
    ),
]
DefinesArg = Annotated[
    dict[str, str | None] | None,
    Field(
        default=None,
        description=(
            "Additional preprocessor defines. Use `{NAME: null}` for valueless defines and "
            '`{NAME: "VALUE"}` for explicit values.'
        ),
    ),
]
TopModulesArg = Annotated[
    list[str] | None,
    Field(
        default=None,
        description=(
            "Optional top-module override passed into pyslang elaboration. Use when the project "
            "contains multiple candidate tops."
        ),
    ),
]
DesignUnitNameArg = Annotated[
    str,
    Field(
        description=(
            "Exact, case-sensitive design-unit name. Call "
            f"`{PUBLIC_TOOL_NAMES['list_design_units']}` first if you need to discover the "
            "available names."
        )
    ),
]
SymbolQueryArg = Annotated[
    str,
    Field(
        description=(
            "Symbol name, lexical path, or hierarchical path to match against declarations and "
            "optionally references."
        )
    ),
]
MatchModeArg = Annotated[
    MatchMode,
    Field(
        default="exact",
        description=(
            "Match mode for `query`: `exact` matches the full name or path, `contains` matches "
            "substrings, and `startswith` matches prefixes."
        ),
    ),
]
IncludeReferencesArg = Annotated[
    bool,
    Field(
        default=True,
        description=(
            "When true, walk the elaborated design to include reference hits. This is more "
            "expensive than declaration-only lookup on larger projects."
        ),
    ),
]
MaxItemsArg = Annotated[
    int,
    Field(
        default=200,
        ge=0,
        le=MAX_LIST_ITEMS,
        description="Maximum number of list items to return before truncation.",
    ),
]
MaxResultsArg = Annotated[
    int,
    Field(
        default=100,
        ge=0,
        le=MAX_SYMBOL_RESULTS,
        description="Maximum declaration hits and maximum reference hits to return.",
    ),
]
MaxDepthArg = Annotated[
    int,
    Field(
        default=8,
        ge=1,
        le=MAX_HIERARCHY_DEPTH,
        description="Maximum hierarchy depth to expand from each top instance.",
    ),
]
MaxChildrenArg = Annotated[
    int,
    Field(
        default=100,
        ge=0,
        le=MAX_HIERARCHY_CHILDREN,
        description="Maximum child instances to return per hierarchy node.",
    ),
]
MaxFilesArg = Annotated[
    int,
    Field(
        default=50,
        ge=0,
        le=MAX_SUMMARY_FILES,
        description="Maximum number of files to summarize before truncation.",
    ),
]
MaxNodeKindsArg = Annotated[
    int,
    Field(
        default=40,
        ge=0,
        le=MAX_NODE_KINDS,
        description="Maximum distinct syntax node kinds to keep per file summary.",
    ),
]
MaxExcerptLinesArg = Annotated[
    int,
    Field(
        default=12,
        ge=0,
        le=MAX_EXCERPT_LINES,
        description="Maximum number of leading source lines to include per file excerpt.",
    ),
]
MaxSummaryDiagnosticsArg = Annotated[
    int,
    Field(
        default=50,
        ge=0,
        le=MAX_LIST_ITEMS,
        description=(
            f"Maximum diagnostics to fold into `{PUBLIC_TOOL_NAMES['get_project_summary']}`."
        ),
    ),
]
MaxSummaryUnitsArg = Annotated[
    int,
    Field(
        default=200,
        ge=0,
        le=MAX_LIST_ITEMS,
        description=(
            f"Maximum design units to fold into `{PUBLIC_TOOL_NAMES['get_project_summary']}`."
        ),
    ),
]
SummaryDepthArg = Annotated[
    int,
    Field(
        default=6,
        ge=1,
        le=MAX_HIERARCHY_DEPTH,
        description=(
            f"Maximum hierarchy depth to fold into `{PUBLIC_TOOL_NAMES['get_project_summary']}`."
        ),
    ),
]
SummaryChildrenArg = Annotated[
    int,
    Field(
        default=100,
        ge=0,
        le=MAX_HIERARCHY_CHILDREN,
        description=(
            f"Maximum child instances per node in `{PUBLIC_TOOL_NAMES['get_project_summary']}`."
        ),
    ),
]

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class ToolInputError(ValueError):
    """Raised when the caller supplies an invalid argument combination."""


def create_server(cache: AnalysisCache | None = None) -> FastMCP:
    """Create the MCP server instance."""

    analysis_cache = cache if cache is not None else DEFAULT_CACHE
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
        if (files is None) == (filelist is None):
            raise ToolInputError("Provide exactly one of `files` or `filelist`.")
        if files is not None:
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

    def success_result(schema: type[SchemaT], payload: dict[str, Any]) -> CallToolResult:
        validated = schema.model_validate(payload)
        structured = validated.model_dump(mode="json", exclude_unset=True)
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(structured, sort_keys=True))],
            structuredContent={"result": structured},
        )

    def error_result(
        *,
        code: str,
        message: str,
        hint: str | None = None,
        details: dict[str, object] | None = None,
    ) -> CallToolResult:
        payload = ToolErrorResult(
            error=ToolErrorDetail(
                code=code,
                message=message,
                hint=hint,
                details=details,
            )
        )
        structured = payload.model_dump(mode="json", exclude_unset=True)
        text = message if hint is None else f"{message}\nHint: {hint}"
        return CallToolResult(
            content=[TextContent(type="text", text=text)],
            structuredContent={"result": structured},
            isError=True,
        )

    def run_tool(schema: type[SchemaT], callback: Callable[[], dict[str, Any]]) -> CallToolResult:
        try:
            return success_result(schema, callback())
        except ToolInputError as exc:
            return error_result(
                code="invalid_arguments",
                message=str(exc),
                hint=(
                    "Pass either `files` or `filelist`, and keep the rest of the "
                    "arguments consistent with that mode."
                ),
            )
        except PathOutsideRootError as exc:
            return error_result(
                code="path_outside_root",
                message=str(exc),
                hint="Keep every requested path under the declared `project_root`.",
            )
        except ProjectLoadError as exc:
            return error_result(
                code="project_load_error",
                message=str(exc),
                hint=(
                    "Verify the project root, filelist entries, include directories, "
                    "and source file paths."
                ),
            )

    @mcp.tool(
        name=PUBLIC_TOOL_NAMES["parse_files"],
        annotations=READ_ONLY_ANNOTATIONS,
        description=(
            "Parse and elaborate an explicit list of Verilog or SystemVerilog files under a "
            "declared project root. Returns the normalized project configuration plus a compact "
            "parse summary with file, include, define, top-module, and diagnostic counts."
        ),
    )
    def parse_files(
        project_root: ProjectRootArg,
        files: FilesArg,
        include_dirs: IncludeDirsArg = None,
        defines: DefinesArg = None,
        top_modules: TopModulesArg = None,
    ) -> Annotated[CallToolResult, ParseFilesResult | ToolErrorResult]:
        return run_tool(
            ParseFilesResult,
            lambda: parse_summary(
                analyze(
                    load_project_from_files(
                        project_root=project_root,
                        files=files,
                        include_dirs=include_dirs,
                        defines=defines,
                        top_modules=top_modules,
                    )
                )
            ),
        )

    @mcp.tool(
        name=PUBLIC_TOOL_NAMES["parse_filelist"],
        annotations=READ_ONLY_ANNOTATIONS,
        description=(
            "Parse and elaborate a project filelist under a declared project root. Returns the "
            "normalized project configuration, parse counts, expanded nested filelists, and any "
            "unsupported filelist directives that were reported instead of ignored."
        ),
    )
    def parse_filelist(
        project_root: ProjectRootArg,
        filelist: FilelistArg,
        include_dirs: IncludeDirsArg = None,
        defines: DefinesArg = None,
        top_modules: TopModulesArg = None,
    ) -> Annotated[CallToolResult, ParseFilelistResult | ToolErrorResult]:
        return run_tool(
            ParseFilelistResult,
            lambda: filelist_summary(
                analyze(
                    load_project_from_filelist(
                        project_root=project_root,
                        filelist=filelist,
                        include_dirs=include_dirs,
                        defines=defines,
                        top_modules=top_modules,
                    )
                )
            ),
        )

    @mcp.tool(
        name=PUBLIC_TOOL_NAMES["get_diagnostics"],
        annotations=READ_ONLY_ANNOTATIONS,
        description=(
            "Return parse and semantic diagnostics for a project described by explicit files or a "
            "filelist. Use this early to confirm the project loads cleanly; the result includes "
            "severity counts, per-diagnostic locations, and truncation metadata."
        ),
    )
    def get_diagnostics(
        project_root: ProjectRootArg,
        files: OptionalFilesArg = None,
        filelist: OptionalFilelistArg = None,
        include_dirs: IncludeDirsArg = None,
        defines: DefinesArg = None,
        top_modules: TopModulesArg = None,
        max_items: MaxItemsArg = 200,
    ) -> Annotated[CallToolResult, DiagnosticsResult | ToolErrorResult]:
        return run_tool(
            DiagnosticsResult,
            lambda: get_diagnostics_core(
                analyze(
                    resolve_project(
                        project_root=project_root,
                        files=files,
                        filelist=filelist,
                        include_dirs=include_dirs,
                        defines=defines,
                        top_modules=top_modules,
                    )
                ),
                max_items=max_items,
            ),
        )

    @mcp.tool(
        name=PUBLIC_TOOL_NAMES["list_design_units"],
        annotations=READ_ONLY_ANNOTATIONS,
        description=(
            "List project-local modules, interfaces, and packages for the analyzed project. Use "
            "this as the discovery step before "
            f"`{PUBLIC_TOOL_NAMES['describe_design_unit']}`; results include stable names, "
            "kinds, paths, locations, and truncation metadata."
        ),
    )
    def list_design_units(
        project_root: ProjectRootArg,
        files: OptionalFilesArg = None,
        filelist: OptionalFilelistArg = None,
        include_dirs: IncludeDirsArg = None,
        defines: DefinesArg = None,
        top_modules: TopModulesArg = None,
        max_items: MaxItemsArg = 200,
    ) -> Annotated[CallToolResult, ListDesignUnitsResult | ToolErrorResult]:
        return run_tool(
            ListDesignUnitsResult,
            lambda: list_design_units_core(
                analyze(
                    resolve_project(
                        project_root=project_root,
                        files=files,
                        filelist=filelist,
                        include_dirs=include_dirs,
                        defines=defines,
                        top_modules=top_modules,
                    )
                ),
                max_items=max_items,
            ),
        )

    @mcp.tool(
        name=PUBLIC_TOOL_NAMES["describe_design_unit"],
        annotations=READ_ONLY_ANNOTATIONS,
        description=(
            "Describe one project-local design unit by exact, case-sensitive name. Start with "
            f"`{PUBLIC_TOOL_NAMES['list_design_units']}` if you need discovery. The result "
            "reports `found` / `ambiguous`, candidate matches, and on success a "
            "`design_unit` object with ports, member-kind counts, child instances, and "
            "declared names."
        ),
    )
    def describe_design_unit(
        project_root: ProjectRootArg,
        name: DesignUnitNameArg,
        files: OptionalFilesArg = None,
        filelist: OptionalFilelistArg = None,
        include_dirs: IncludeDirsArg = None,
        defines: DefinesArg = None,
        top_modules: TopModulesArg = None,
    ) -> Annotated[CallToolResult, DescribeDesignUnitResult | ToolErrorResult]:
        return run_tool(
            DescribeDesignUnitResult,
            lambda: describe_design_unit_core(
                analyze(
                    resolve_project(
                        project_root=project_root,
                        files=files,
                        filelist=filelist,
                        include_dirs=include_dirs,
                        defines=defines,
                        top_modules=top_modules,
                    )
                ),
                name=name,
            ),
        )

    @mcp.tool(
        name=PUBLIC_TOOL_NAMES["get_hierarchy"],
        annotations=READ_ONLY_ANNOTATIONS,
        description=(
            "Return the elaborated instance hierarchy rooted at pyslang top instances. Use "
            "`max_depth` and `max_children` to control expansion; nodes include definitions, "
            "locations, port-connection snippets, and child truncation markers."
        ),
    )
    def get_hierarchy(
        project_root: ProjectRootArg,
        files: OptionalFilesArg = None,
        filelist: OptionalFilelistArg = None,
        include_dirs: IncludeDirsArg = None,
        defines: DefinesArg = None,
        top_modules: TopModulesArg = None,
        max_depth: MaxDepthArg = 8,
        max_children: MaxChildrenArg = 100,
    ) -> Annotated[CallToolResult, HierarchyResult | ToolErrorResult]:
        return run_tool(
            HierarchyResult,
            lambda: get_hierarchy_core(
                analyze(
                    resolve_project(
                        project_root=project_root,
                        files=files,
                        filelist=filelist,
                        include_dirs=include_dirs,
                        defines=defines,
                        top_modules=top_modules,
                    )
                ),
                max_depth=max_depth,
                max_children=max_children,
            ),
        )

    @mcp.tool(
        name=PUBLIC_TOOL_NAMES["find_symbol"],
        annotations=READ_ONLY_ANNOTATIONS,
        description=(
            "Search declarations and references by symbol name, lexical path, or hierarchical "
            "path. `match_mode` accepts `exact`, `contains`, or `startswith`. Reference hits can "
            "include `named_value`, `package_import`, `instance_definition`, and `declared_type`; "
            "set `include_references=false` for a cheaper declaration-only query."
        ),
    )
    def find_symbol(
        project_root: ProjectRootArg,
        query: SymbolQueryArg,
        files: OptionalFilesArg = None,
        filelist: OptionalFilelistArg = None,
        include_dirs: IncludeDirsArg = None,
        defines: DefinesArg = None,
        top_modules: TopModulesArg = None,
        match_mode: MatchModeArg = "exact",
        include_references: IncludeReferencesArg = True,
        max_results: MaxResultsArg = 100,
    ) -> Annotated[CallToolResult, FindSymbolResult | ToolErrorResult]:
        return run_tool(
            FindSymbolResult,
            lambda: find_symbol_core(
                analyze(
                    resolve_project(
                        project_root=project_root,
                        files=files,
                        filelist=filelist,
                        include_dirs=include_dirs,
                        defines=defines,
                        top_modules=top_modules,
                    )
                ),
                query=query,
                match_mode=match_mode,
                include_references=include_references,
                max_results=max_results,
            ),
        )

    @mcp.tool(
        name=PUBLIC_TOOL_NAMES["dump_syntax_tree_summary"],
        annotations=READ_ONLY_ANNOTATIONS,
        description=(
            "Summarize syntax-tree shapes per file without dumping full raw ASTs. Returns each "
            "file's root kind, top-level member kinds, include directives, and the most common "
            "node kinds up to `max_node_kinds`."
        ),
    )
    def dump_syntax_tree_summary(
        project_root: ProjectRootArg,
        files: OptionalFilesArg = None,
        filelist: OptionalFilelistArg = None,
        include_dirs: IncludeDirsArg = None,
        defines: DefinesArg = None,
        top_modules: TopModulesArg = None,
        max_files: MaxFilesArg = 50,
        max_node_kinds: MaxNodeKindsArg = 40,
    ) -> Annotated[CallToolResult, SyntaxTreeSummaryResult | ToolErrorResult]:
        return run_tool(
            SyntaxTreeSummaryResult,
            lambda: dump_syntax_tree_summary_core(
                analyze(
                    resolve_project(
                        project_root=project_root,
                        files=files,
                        filelist=filelist,
                        include_dirs=include_dirs,
                        defines=defines,
                        top_modules=top_modules,
                    )
                ),
                max_files=max_files,
                max_node_kinds=max_node_kinds,
            ),
        )

    @mcp.tool(
        name=PUBLIC_TOOL_NAMES["preprocess_files"],
        annotations=READ_ONLY_ANNOTATIONS,
        description=(
            "Return conservative preprocessing metadata and leading source excerpts for analyzed "
            "files. This is summary-only: it reports include directives and effective defines, "
            "but it does not claim to produce a full standalone preprocessed text stream."
        ),
    )
    def preprocess_files(
        project_root: ProjectRootArg,
        files: OptionalFilesArg = None,
        filelist: OptionalFilelistArg = None,
        include_dirs: IncludeDirsArg = None,
        defines: DefinesArg = None,
        top_modules: TopModulesArg = None,
        max_files: MaxFilesArg = 50,
        max_excerpt_lines: MaxExcerptLinesArg = 12,
    ) -> Annotated[CallToolResult, PreprocessFilesResult | ToolErrorResult]:
        return run_tool(
            PreprocessFilesResult,
            lambda: preprocess_files_core(
                analyze(
                    resolve_project(
                        project_root=project_root,
                        files=files,
                        filelist=filelist,
                        include_dirs=include_dirs,
                        defines=defines,
                        top_modules=top_modules,
                    )
                ),
                max_files=max_files,
                max_excerpt_lines=max_excerpt_lines,
            ),
        )

    @mcp.tool(
        name=PUBLIC_TOOL_NAMES["get_project_summary"],
        annotations=READ_ONLY_ANNOTATIONS,
        description=(
            "Return a compact project-wide summary of normalized inputs, diagnostics, design-unit "
            "counts, top instances, and tracked paths. The summary uses bounded internal limits; "
            "tune them with `max_diagnostics`, `max_design_units`, `max_depth`, and "
            "`max_children`."
        ),
    )
    def get_project_summary(
        project_root: ProjectRootArg,
        files: OptionalFilesArg = None,
        filelist: OptionalFilelistArg = None,
        include_dirs: IncludeDirsArg = None,
        defines: DefinesArg = None,
        top_modules: TopModulesArg = None,
        max_diagnostics: MaxSummaryDiagnosticsArg = 50,
        max_design_units: MaxSummaryUnitsArg = 200,
        max_depth: SummaryDepthArg = 6,
        max_children: SummaryChildrenArg = 100,
    ) -> Annotated[CallToolResult, ProjectSummaryResult | ToolErrorResult]:
        return run_tool(
            ProjectSummaryResult,
            lambda: get_project_summary_core(
                analyze(
                    resolve_project(
                        project_root=project_root,
                        files=files,
                        filelist=filelist,
                        include_dirs=include_dirs,
                        defines=defines,
                        top_modules=top_modules,
                    )
                ),
                max_diagnostics=max_diagnostics,
                max_design_units=max_design_units,
                max_depth=max_depth,
                max_children=max_children,
            ),
        )

    return mcp
