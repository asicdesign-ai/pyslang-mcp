"""Pydantic schemas for MCP tool inputs and outputs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    """Base schema with stable field validation."""

    model_config = ConfigDict(extra="forbid")


class ToolErrorDetail(StrictModel):
    code: str
    message: str
    hint: str | None = None
    details: dict[str, object] | None = None


class ToolErrorResult(StrictModel):
    error: ToolErrorDetail


class TruncationInfo(StrictModel):
    returned: int
    total: int
    truncated: bool
    remaining: int


class Location(StrictModel):
    path: str
    line: int
    column: int
    end_line: int | None = None
    end_column: int | None = None


class ProjectStatus(StrictModel):
    status: Literal["ok", "degraded", "incomplete"]
    diagnostic_count: int
    error_count: int
    warning_count: int
    unresolved_references: int


class ProjectConfigSchema(StrictModel):
    project_root: str
    source: Literal["files", "filelist"]
    primary_input: str | None = None
    files: list[str]
    include_dirs: list[str]
    defines: dict[str, str | None]
    top_modules: list[str]
    filelists: list[str]
    unsupported_filelist_entries: list[str]


class ParseSummary(StrictModel):
    file_count: int
    include_dir_count: int
    define_count: int
    top_module_count: int
    diagnostic_count: int
    diagnostic_severity_counts: dict[str, int]


class ParseFilesResult(StrictModel):
    project_status: ProjectStatus
    project: ProjectConfigSchema
    parse: ParseSummary


class FilelistSummary(StrictModel):
    primary_input: str | None = None
    filelists: list[str]
    unsupported_entries: list[str]


class ParseFilelistResult(ParseFilesResult):
    filelist: FilelistSummary


class DiagnosticEntry(StrictModel):
    code: str
    severity: str
    message: str
    args: list[str]
    location: Location | None = None
    line_excerpt: str | None = None
    is_error: bool


class DiagnosticsSummary(StrictModel):
    total: int
    severity_counts: dict[str, int]
    truncation: TruncationInfo


class DiagnosticsResult(StrictModel):
    project_status: ProjectStatus
    project_root: str
    summary: DiagnosticsSummary
    diagnostics: list[DiagnosticEntry]


class DesignUnitRecord(StrictModel):
    name: str
    kind: str
    symbol_kind: str
    hierarchical_path: str
    lexical_path: str
    instance_count: int | None = None
    location: Location | None = None


class DesignUnitListSummary(StrictModel):
    total: int
    by_kind: dict[str, int]
    truncation: TruncationInfo


class ListDesignUnitsResult(StrictModel):
    project_status: ProjectStatus
    summary: DesignUnitListSummary
    design_units: list[DesignUnitRecord]


class PortRecord(StrictModel):
    name: str
    direction: str | None = None
    data_type_kind: str | None = None


class ChildInstanceRecord(StrictModel):
    name: str
    definition: str | None = None


class DesignUnitDescription(DesignUnitRecord):
    ports: list[PortRecord]
    member_kind_counts: dict[str, int]
    child_instances: list[ChildInstanceRecord]
    declared_names: list[str]


class DescribeDesignUnitResult(StrictModel):
    project_status: ProjectStatus
    query: str
    found: bool
    ambiguous: bool
    candidates: list[DesignUnitRecord]
    design_unit: DesignUnitDescription | None = None


class HierarchyPortConnection(StrictModel):
    port: str
    expression_kind: str
    snippet: str | None = None
    symbol: str | None = None


class HierarchyNode(StrictModel):
    name: str
    definition: str | None = None
    hierarchical_path: str
    location: Location | None = None
    port_connections: list[HierarchyPortConnection]
    children: list[HierarchyNode] = Field(default_factory=list)
    truncated_children: int | None = None


class HierarchySummary(StrictModel):
    top_instances: list[str]
    total_instances: int
    max_depth_requested: int


class HierarchyResult(StrictModel):
    project_status: ProjectStatus
    summary: HierarchySummary
    hierarchy: list[HierarchyNode]


class SymbolDeclaration(StrictModel):
    name: str | None = None
    kind: str
    hierarchical_path: str
    lexical_path: str
    location: Location | None = None


class SymbolReference(StrictModel):
    name: str | None = None
    target_kind: str
    target_path: str
    reference_kind: str
    location: Location | None = None
    snippet: str | None = None


class FindSymbolSummary(StrictModel):
    declaration_count: int
    reference_count: int
    declaration_truncation: TruncationInfo
    reference_truncation: TruncationInfo


class FindSymbolResult(StrictModel):
    project_status: ProjectStatus
    query: str
    match_mode: Literal["exact", "contains", "startswith"]
    declarations: list[SymbolDeclaration]
    references: list[SymbolReference]
    summary: FindSymbolSummary


class IncludeDirective(StrictModel):
    path: str
    is_system: bool


class SyntaxFileSummary(StrictModel):
    file: str
    root_kind: str
    top_level_members: list[str]
    node_kind_counts: dict[str, int]
    include_directives: list[IncludeDirective]


class SyntaxTreeSummaryMeta(StrictModel):
    file_count: int
    truncation: TruncationInfo


class SyntaxTreeSummaryResult(StrictModel):
    project_status: ProjectStatus
    summary: SyntaxTreeSummaryMeta
    files: list[SyntaxFileSummary]


class PreprocessFileSummary(StrictModel):
    file: str
    include_directives: list[IncludeDirective]
    source_excerpt: str


class PreprocessSummary(StrictModel):
    file_count: int
    truncation: TruncationInfo


class PreprocessFilesResult(StrictModel):
    project_status: ProjectStatus
    mode: Literal["summary_only"]
    note: str
    summary: PreprocessSummary
    effective_defines: dict[str, str | None]
    files: list[PreprocessFileSummary]


class ProjectSummaryLimits(StrictModel):
    max_diagnostics: int
    max_design_units: int
    max_depth: int
    max_children: int


class ProjectSummaryResult(StrictModel):
    project_status: ProjectStatus
    project: ProjectConfigSchema
    summary: ParseSummary
    diagnostics: DiagnosticsSummary
    design_units: DesignUnitListSummary
    top_instances: list[str]
    tracked_paths: list[str]
    limits: ProjectSummaryLimits


HierarchyNode.model_rebuild()
