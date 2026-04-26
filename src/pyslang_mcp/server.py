"""FastMCP server wiring for pyslang-mcp."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Annotated, Any, TypeVar, cast

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import BaseModel, Field, ValidationError

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
        json_schema_extra={"minItems": 1},
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
    str,
    Field(
        default="exact",
        description=(
            "Match mode for `query`: `exact` matches the full name or path, `contains` matches "
            "substrings, and `startswith` matches prefixes."
        ),
        json_schema_extra={"enum": ["exact", "contains", "startswith"]},
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
        description="Maximum number of list items to return before truncation.",
        json_schema_extra={"minimum": 0, "maximum": MAX_LIST_ITEMS},
    ),
]
MaxResultsArg = Annotated[
    int,
    Field(
        default=100,
        description="Maximum declaration hits and maximum reference hits to return.",
        json_schema_extra={"minimum": 0, "maximum": MAX_SYMBOL_RESULTS},
    ),
]
MaxDepthArg = Annotated[
    int,
    Field(
        default=8,
        description="Maximum hierarchy depth to expand from each top instance.",
        json_schema_extra={"minimum": 1, "maximum": MAX_HIERARCHY_DEPTH},
    ),
]
MaxChildrenArg = Annotated[
    int,
    Field(
        default=100,
        description="Maximum child instances to return per hierarchy node.",
        json_schema_extra={"minimum": 0, "maximum": MAX_HIERARCHY_CHILDREN},
    ),
]
MaxFilesArg = Annotated[
    int,
    Field(
        default=50,
        description="Maximum number of files to summarize before truncation.",
        json_schema_extra={"minimum": 0, "maximum": MAX_SUMMARY_FILES},
    ),
]
MaxNodeKindsArg = Annotated[
    int,
    Field(
        default=40,
        description="Maximum distinct syntax node kinds to keep per file summary.",
        json_schema_extra={"minimum": 0, "maximum": MAX_NODE_KINDS},
    ),
]
MaxExcerptLinesArg = Annotated[
    int,
    Field(
        default=12,
        description="Maximum number of leading source lines to include per file excerpt.",
        json_schema_extra={"minimum": 0, "maximum": MAX_EXCERPT_LINES},
    ),
]
MaxSummaryDiagnosticsArg = Annotated[
    int,
    Field(
        default=50,
        description=(
            f"Maximum diagnostics to fold into `{PUBLIC_TOOL_NAMES['get_project_summary']}`."
        ),
        json_schema_extra={"minimum": 0, "maximum": MAX_LIST_ITEMS},
    ),
]
MaxSummaryUnitsArg = Annotated[
    int,
    Field(
        default=200,
        description=(
            f"Maximum design units to fold into `{PUBLIC_TOOL_NAMES['get_project_summary']}`."
        ),
        json_schema_extra={"minimum": 0, "maximum": MAX_LIST_ITEMS},
    ),
]
SummaryDepthArg = Annotated[
    int,
    Field(
        default=6,
        description=(
            f"Maximum hierarchy depth to fold into `{PUBLIC_TOOL_NAMES['get_project_summary']}`."
        ),
        json_schema_extra={"minimum": 1, "maximum": MAX_HIERARCHY_DEPTH},
    ),
]
SummaryChildrenArg = Annotated[
    int,
    Field(
        default=100,
        description=(
            f"Maximum child instances per node in `{PUBLIC_TOOL_NAMES['get_project_summary']}`."
        ),
        json_schema_extra={"minimum": 0, "maximum": MAX_HIERARCHY_CHILDREN},
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

    def bounded_int(name: str, value: int, *, minimum: int, maximum: int) -> int:
        if value < minimum or value > maximum:
            raise ToolInputError(f"`{name}` must be between {minimum} and {maximum}.")
        return value

    def validate_match_mode(match_mode: str) -> MatchMode:
        valid_modes = {"exact", "contains", "startswith"}
        if match_mode not in valid_modes:
            raise ToolInputError(
                "`match_mode` must be one of `exact`, `contains`, or `startswith`."
            )
        return cast(MatchMode, match_mode)

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
        except UnicodeDecodeError:
            return error_result(
                code="file_read_error",
                message="Could not read a requested file as UTF-8.",
                hint="Check that project files and filelists are text files encoded as UTF-8.",
            )
        except OSError as exc:
            return error_result(
                code="file_read_error",
                message="Could not read a requested file.",
                hint="Verify that the file exists, is readable, and is not a directory.",
                details={"error_type": type(exc).__name__},
            )
        except ValidationError as exc:
            return error_result(
                code="internal_schema_error",
                message="Tool produced a result that did not match its declared schema.",
                hint="Please report this as a pyslang-mcp bug with the tool name and inputs.",
                details={"error_count": len(exc.errors())},
            )
        except Exception as exc:
            return error_result(
                code="analysis_error",
                message="Analysis failed while running the tool.",
                hint=(
                    "Run diagnostics first and verify the file set, include directories, "
                    "defines, and top-module selection."
                ),
                details={"error_type": type(exc).__name__},
            )

    def run_project_tool(
        schema: type[SchemaT],
        *,
        tool_name: str,
        tool_args: dict[str, object] | None,
        project_factory: Callable[[], ProjectConfig],
        callback: Callable[[Any], dict[str, Any]],
    ) -> CallToolResult:
        def compute_payload() -> dict[str, Any]:
            project = project_factory()
            return analysis_cache.get_or_compute_tool_result(
                project,
                tool_name=tool_name,
                tool_args=tool_args,
                bundle_factory=lambda: build_analysis(project),
                result_factory=callback,
            )

        return run_tool(schema, compute_payload)

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
        return run_project_tool(
            ParseFilesResult,
            tool_name="parse_files",
            tool_args={},
            project_factory=lambda: load_project_from_files(
                project_root=project_root,
                files=files,
                include_dirs=include_dirs,
                defines=defines,
                top_modules=top_modules,
            ),
            callback=parse_summary,
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
        return run_project_tool(
            ParseFilelistResult,
            tool_name="parse_filelist",
            tool_args={},
            project_factory=lambda: load_project_from_filelist(
                project_root=project_root,
                filelist=filelist,
                include_dirs=include_dirs,
                defines=defines,
                top_modules=top_modules,
            ),
            callback=filelist_summary,
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
        return run_project_tool(
            DiagnosticsResult,
            tool_name="get_diagnostics",
            tool_args={"max_items": max_items},
            project_factory=lambda: resolve_project(
                project_root=project_root,
                files=files,
                filelist=filelist,
                include_dirs=include_dirs,
                defines=defines,
                top_modules=top_modules,
            ),
            callback=lambda bundle: get_diagnostics_core(
                bundle,
                max_items=bounded_int(
                    "max_items",
                    max_items,
                    minimum=0,
                    maximum=MAX_LIST_ITEMS,
                ),
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
        return run_project_tool(
            ListDesignUnitsResult,
            tool_name="list_design_units",
            tool_args={"max_items": max_items},
            project_factory=lambda: resolve_project(
                project_root=project_root,
                files=files,
                filelist=filelist,
                include_dirs=include_dirs,
                defines=defines,
                top_modules=top_modules,
            ),
            callback=lambda bundle: list_design_units_core(
                bundle,
                max_items=bounded_int(
                    "max_items",
                    max_items,
                    minimum=0,
                    maximum=MAX_LIST_ITEMS,
                ),
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
        return run_project_tool(
            DescribeDesignUnitResult,
            tool_name="describe_design_unit",
            tool_args={"name": name},
            project_factory=lambda: resolve_project(
                project_root=project_root,
                files=files,
                filelist=filelist,
                include_dirs=include_dirs,
                defines=defines,
                top_modules=top_modules,
            ),
            callback=lambda bundle: describe_design_unit_core(
                bundle,
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
        return run_project_tool(
            HierarchyResult,
            tool_name="get_hierarchy",
            tool_args={
                "max_depth": max_depth,
                "max_children": max_children,
            },
            project_factory=lambda: resolve_project(
                project_root=project_root,
                files=files,
                filelist=filelist,
                include_dirs=include_dirs,
                defines=defines,
                top_modules=top_modules,
            ),
            callback=lambda bundle: get_hierarchy_core(
                bundle,
                max_depth=bounded_int(
                    "max_depth",
                    max_depth,
                    minimum=1,
                    maximum=MAX_HIERARCHY_DEPTH,
                ),
                max_children=bounded_int(
                    "max_children",
                    max_children,
                    minimum=0,
                    maximum=MAX_HIERARCHY_CHILDREN,
                ),
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
        return run_project_tool(
            FindSymbolResult,
            tool_name="find_symbol",
            tool_args={
                "query": query,
                "match_mode": match_mode,
                "include_references": include_references,
                "max_results": max_results,
            },
            project_factory=lambda: resolve_project(
                project_root=project_root,
                files=files,
                filelist=filelist,
                include_dirs=include_dirs,
                defines=defines,
                top_modules=top_modules,
            ),
            callback=lambda bundle: find_symbol_core(
                bundle,
                query=query,
                match_mode=validate_match_mode(match_mode),
                include_references=include_references,
                max_results=bounded_int(
                    "max_results",
                    max_results,
                    minimum=0,
                    maximum=MAX_SYMBOL_RESULTS,
                ),
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
        return run_project_tool(
            SyntaxTreeSummaryResult,
            tool_name="dump_syntax_tree_summary",
            tool_args={
                "max_files": max_files,
                "max_node_kinds": max_node_kinds,
            },
            project_factory=lambda: resolve_project(
                project_root=project_root,
                files=files,
                filelist=filelist,
                include_dirs=include_dirs,
                defines=defines,
                top_modules=top_modules,
            ),
            callback=lambda bundle: dump_syntax_tree_summary_core(
                bundle,
                max_files=bounded_int(
                    "max_files",
                    max_files,
                    minimum=0,
                    maximum=MAX_SUMMARY_FILES,
                ),
                max_node_kinds=bounded_int(
                    "max_node_kinds",
                    max_node_kinds,
                    minimum=0,
                    maximum=MAX_NODE_KINDS,
                ),
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
        return run_project_tool(
            PreprocessFilesResult,
            tool_name="preprocess_files",
            tool_args={
                "max_files": max_files,
                "max_excerpt_lines": max_excerpt_lines,
            },
            project_factory=lambda: resolve_project(
                project_root=project_root,
                files=files,
                filelist=filelist,
                include_dirs=include_dirs,
                defines=defines,
                top_modules=top_modules,
            ),
            callback=lambda bundle: preprocess_files_core(
                bundle,
                max_files=bounded_int(
                    "max_files",
                    max_files,
                    minimum=0,
                    maximum=MAX_SUMMARY_FILES,
                ),
                max_excerpt_lines=bounded_int(
                    "max_excerpt_lines",
                    max_excerpt_lines,
                    minimum=0,
                    maximum=MAX_EXCERPT_LINES,
                ),
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
        return run_project_tool(
            ProjectSummaryResult,
            tool_name="get_project_summary",
            tool_args={
                "max_diagnostics": max_diagnostics,
                "max_design_units": max_design_units,
                "max_depth": max_depth,
                "max_children": max_children,
            },
            project_factory=lambda: resolve_project(
                project_root=project_root,
                files=files,
                filelist=filelist,
                include_dirs=include_dirs,
                defines=defines,
                top_modules=top_modules,
            ),
            callback=lambda bundle: get_project_summary_core(
                bundle,
                max_diagnostics=bounded_int(
                    "max_diagnostics",
                    max_diagnostics,
                    minimum=0,
                    maximum=MAX_LIST_ITEMS,
                ),
                max_design_units=bounded_int(
                    "max_design_units",
                    max_design_units,
                    minimum=0,
                    maximum=MAX_LIST_ITEMS,
                ),
                max_depth=bounded_int(
                    "max_depth",
                    max_depth,
                    minimum=1,
                    maximum=MAX_HIERARCHY_DEPTH,
                ),
                max_children=bounded_int(
                    "max_children",
                    max_children,
                    minimum=0,
                    maximum=MAX_HIERARCHY_CHILDREN,
                ),
            ),
        )

    return mcp
