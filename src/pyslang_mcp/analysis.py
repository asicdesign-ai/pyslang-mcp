"""Core pyslang-backed analysis functions."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal

from pyslang import (
    Bag,
    Compilation,
    CompilationOptions,
    DiagnosticEngine,
    PreprocessorOptions,
    SourceManager,
    SyntaxTree,
)

from .serializers import (
    ensure_jsonable_paths,
    limit_list,
    project_config_json,
    relative_path,
    stabilize_json,
    top_counts,
)
from .types import (
    AnalysisBundle,
    AnalysisIndex,
    IndexedDeclaration,
    IndexedReference,
    ProjectConfig,
)

MatchMode = Literal["exact", "contains", "startswith"]


def build_analysis(project: ProjectConfig) -> AnalysisBundle:
    """Compile a normalized project config into a reusable analysis bundle."""

    source_manager = SourceManager()
    for include_dir in project.include_dirs:
        source_manager.addUserDirectories(str(include_dir))

    bag = Bag()
    if project.include_dirs or project.defines:
        pp_options = PreprocessorOptions()
        if project.include_dirs:
            pp_options.additionalIncludePaths = [str(path) for path in project.include_dirs]
        predefines = []
        for key, value in project.defines:
            predefines.append(key if value is None else f"{key}={value}")
        if predefines:
            pp_options.predefines = predefines
        bag.preprocessorOptions = pp_options
    if project.top_modules:
        compilation_options = CompilationOptions()
        compilation_options.topModules = set(project.top_modules)
        bag.compilationOptions = compilation_options

    compilation = Compilation(bag)
    syntax_trees: dict[Path, Any] = {}
    for file_path in project.files:
        tree = SyntaxTree.fromFile(str(file_path), source_manager, bag)
        syntax_trees[file_path] = tree
        compilation.addSyntaxTree(tree)

    tracked_paths = _tracked_paths(project, source_manager)
    bundle = AnalysisBundle(
        project=project,
        source_manager=source_manager,
        bag=bag,
        compilation=compilation,
        syntax_trees=syntax_trees,
        diagnostic_engine=DiagnosticEngine(source_manager),
        tracked_paths=tracked_paths,
    )
    bundle.index = _build_index(bundle)
    return bundle


def parse_summary(bundle: AnalysisBundle) -> dict[str, Any]:
    """Return a concise parse summary for explicit file mode."""

    return stabilize_json(
        {
            "project_status": _project_status(bundle),
            "project": project_config_json(bundle.project),
            "parse": _base_summary(bundle),
        }
    )


def filelist_summary(bundle: AnalysisBundle) -> dict[str, Any]:
    """Return a concise parse summary for filelist mode."""

    return stabilize_json(
        {
            "project_status": _project_status(bundle),
            "project": project_config_json(bundle.project),
            "parse": _base_summary(bundle),
            "filelist": {
                "primary_input": (
                    relative_path(bundle.project.project_root, bundle.project.primary_input)
                    if bundle.project.primary_input
                    else None
                ),
                "filelists": ensure_jsonable_paths(
                    bundle.project.filelists, bundle.project.project_root
                ),
                "unsupported_entries": list(bundle.project.unsupported_filelist_entries),
            },
        }
    )


def get_project_summary(
    bundle: AnalysisBundle,
    *,
    max_diagnostics: int = 50,
    max_design_units: int = 200,
    max_depth: int = 6,
    max_children: int = 100,
) -> dict[str, Any]:
    """Return a compact project-wide summary."""

    diagnostics = get_diagnostics(bundle, max_items=max_diagnostics)
    units = list_design_units(bundle, max_items=max_design_units)
    hierarchy = get_hierarchy(bundle, max_depth=max_depth, max_children=max_children)
    summary = {
        "project_status": _project_status(bundle),
        "project": project_config_json(bundle.project),
        "summary": _base_summary(bundle),
        "diagnostics": diagnostics["summary"],
        "design_units": units["summary"],
        "top_instances": hierarchy["summary"]["top_instances"],
        "tracked_paths": ensure_jsonable_paths(bundle.tracked_paths, bundle.project.project_root),
        "limits": {
            "max_diagnostics": max_diagnostics,
            "max_design_units": max_design_units,
            "max_depth": max_depth,
            "max_children": max_children,
        },
    }
    return stabilize_json(summary)


def get_diagnostics(bundle: AnalysisBundle, *, max_items: int = 200) -> dict[str, Any]:
    """Return parse and semantic diagnostics."""

    diagnostics_json: list[dict[str, Any]] = []
    severity_counts: Counter[str] = Counter()
    total = 0
    for diagnostic in bundle.compilation.getAllDiagnostics():
        total += 1
        severity = bundle.diagnostic_engine.getSeverity(
            diagnostic.code, diagnostic.location
        ).name.lower()
        severity_counts[severity] += 1
        if len(diagnostics_json) < max(max_items, 0):
            diagnostics_json.append(_serialize_diagnostic(bundle, diagnostic))

    return stabilize_json(
        {
            "project_status": _project_status(bundle),
            "project_root": bundle.project.project_root.as_posix(),
            "summary": {
                "total": total,
                "severity_counts": dict(sorted(severity_counts.items())),
                "truncation": _truncation(returned=len(diagnostics_json), total=total),
            },
            "diagnostics": diagnostics_json,
        }
    )


def list_design_units(bundle: AnalysisBundle, *, max_items: int = 200) -> dict[str, Any]:
    """List project-local modules, interfaces, and packages."""

    units = list(_analysis_index(bundle).design_unit_records)

    units_json, truncation = limit_list(units, max_items=max_items)
    type_counts = Counter(str(unit["kind"]) for unit in units)
    return stabilize_json(
        {
            "project_status": _project_status(bundle),
            "summary": {
                "total": len(units),
                "by_kind": dict(sorted(type_counts.items())),
                "truncation": truncation,
            },
            "design_units": units_json,
        }
    )


def describe_design_unit(bundle: AnalysisBundle, *, name: str) -> dict[str, Any]:
    """Describe a single project-local design unit by exact name."""

    index = _analysis_index(bundle)
    local_records = list(index.design_unit_records)
    exact_matches = [record for record in local_records if record["name"] == name]
    if len(exact_matches) != 1:
        suggestions = [
            record
            for record in local_records
            if _matches_text(
                query=name,
                match_mode="contains",
                candidates={record["name"], record["hierarchical_path"], record["lexical_path"]},
            )
            or str(record["name"]).lower() == name.lower()
            or str(record["name"]).lower().startswith(name.lower())
        ][:10]
        return stabilize_json(
            {
                "project_status": _project_status(bundle),
                "query": name,
                "found": False,
                "ambiguous": len(exact_matches) > 1,
                "candidates": exact_matches or suggestions,
                "design_unit": None,
            }
        )

    selected_path = str(exact_matches[0]["hierarchical_path"])
    cached = index.design_unit_description_cache.get(selected_path)
    if cached is not None:
        return stabilize_json(cached)

    symbol = index.design_unit_symbols_by_key[(name, selected_path)]
    syntax_json = json.loads(symbol.syntax.to_json())
    member_counts = Counter(_collect_member_kinds(syntax_json.get("members", [])))
    description = {
        "query": name,
        "project_status": _project_status(bundle),
        "found": True,
        "ambiguous": False,
        "candidates": [],
        "design_unit": {
            "name": symbol.name,
            "kind": getattr(getattr(symbol, "definitionKind", None), "name", symbol.kind.name),
            "symbol_kind": symbol.kind.name,
            "hierarchical_path": str(symbol.hierarchicalPath),
            "lexical_path": str(symbol.lexicalPath),
            "location": _serialize_location(bundle, symbol.location),
            "ports": _extract_ports(syntax_json),
            "member_kind_counts": dict(sorted(member_counts.items())),
            "child_instances": _extract_child_instances(syntax_json),
            "declared_names": _extract_declared_names(syntax_json),
            "instance_count": getattr(symbol, "instanceCount", None),
        },
    }
    stable = stabilize_json(description)
    index.design_unit_description_cache[selected_path] = stable
    return stable


def get_hierarchy(
    bundle: AnalysisBundle,
    *,
    max_depth: int = 8,
    max_children: int = 100,
) -> dict[str, Any]:
    """Return the elaborated instance hierarchy from `root.topInstances`."""

    index = _analysis_index(bundle)
    instance_records = index.instance_records_by_path
    children_map = index.children_by_parent

    def build_node(path: str, depth: int) -> dict[str, Any]:
        child_paths = children_map.get(path, [])
        node = {
            **instance_records[path],
            "port_connections": list(instance_records[path]["port_connections"]),
        }
        if depth >= max_depth:
            if child_paths:
                node["children"] = []
                node["truncated_children"] = len(child_paths)
            return node

        limited_children = child_paths[:max_children]
        node["children"] = [build_node(child_path, depth + 1) for child_path in limited_children]
        if len(child_paths) > len(limited_children):
            node["truncated_children"] = len(child_paths) - len(limited_children)
        return node

    hierarchy = [
        build_node(path, depth=1) for path in index.top_instance_paths if path in instance_records
    ]
    return stabilize_json(
        {
            "project_status": _project_status(bundle),
            "summary": {
                "top_instances": [node["hierarchical_path"] for node in hierarchy],
                "total_instances": len(instance_records),
                "max_depth_requested": max_depth,
            },
            "hierarchy": hierarchy,
        }
    )


def find_symbol(
    bundle: AnalysisBundle,
    *,
    query: str,
    match_mode: MatchMode = "exact",
    include_references: bool = True,
    max_results: int = 100,
) -> dict[str, Any]:
    """Find declarations and references matching a symbol name or hierarchical path."""

    index = _analysis_index(bundle)
    declarations, decl_truncation = _filter_indexed_outputs(
        index.declarations,
        query=query,
        match_mode=match_mode,
        max_items=max_results,
    )
    references, ref_truncation = (
        _filter_indexed_outputs(
            index.references,
            query=query,
            match_mode=match_mode,
            max_items=max_results,
        )
        if include_references
        else ([], _truncation(returned=0, total=0))
    )
    return stabilize_json(
        {
            "project_status": _project_status(bundle),
            "query": query,
            "match_mode": match_mode,
            "declarations": declarations,
            "references": references,
            "summary": {
                "declaration_count": decl_truncation["total"],
                "reference_count": ref_truncation["total"],
                "declaration_truncation": decl_truncation,
                "reference_truncation": ref_truncation,
            },
        }
    )


def dump_syntax_tree_summary(
    bundle: AnalysisBundle,
    *,
    max_files: int = 50,
    max_node_kinds: int = 40,
) -> dict[str, Any]:
    """Summarize syntax tree shapes without dumping raw ASTs."""

    sorted_trees = sorted(bundle.syntax_trees.items())
    file_summaries: list[dict[str, Any]] = []
    for file_path, tree in sorted_trees[: max(max_files, 0)]:
        kind_counts: Counter[str] = Counter()

        def visit(node: Any, _kind_counts: Counter[str] = kind_counts) -> bool:
            _kind_counts[node.kind.name] += 1
            return True

        tree.root.visit(visit)
        top_level_members = [member.kind.name for member in getattr(tree.root, "members", [])]
        includes = [
            {
                "path": include.path,
                "is_system": include.isSystem,
            }
            for include in tree.getIncludeDirectives()
        ]
        file_summaries.append(
            {
                "file": relative_path(bundle.project.project_root, file_path),
                "root_kind": tree.root.kind.name,
                "top_level_members": top_level_members,
                "node_kind_counts": top_counts(kind_counts, max_items=max_node_kinds),
                "include_directives": includes,
            }
        )

    return stabilize_json(
        {
            "project_status": _project_status(bundle),
            "summary": {
                "file_count": len(sorted_trees),
                "truncation": _truncation(
                    returned=len(file_summaries),
                    total=len(sorted_trees),
                ),
            },
            "files": file_summaries,
        }
    )


def preprocess_files(
    bundle: AnalysisBundle,
    *,
    max_files: int = 50,
    max_excerpt_lines: int = 12,
) -> dict[str, Any]:
    """Return conservative preprocessing metadata and source excerpts."""

    sorted_trees = sorted(bundle.syntax_trees.items())
    results: list[dict[str, Any]] = []
    for file_path, tree in sorted_trees[: max(max_files, 0)]:
        excerpt = _read_leading_lines(file_path, max_excerpt_lines)
        results.append(
            {
                "file": relative_path(bundle.project.project_root, file_path),
                "include_directives": [
                    {
                        "path": include.path,
                        "is_system": include.isSystem,
                    }
                    for include in tree.getIncludeDirectives()
                ],
                "source_excerpt": excerpt,
            }
        )

    return stabilize_json(
        {
            "project_status": _project_status(bundle),
            "mode": "summary_only",
            "note": (
                "This tool returns preprocessing metadata and source excerpts. "
                "A full standalone preprocessed text stream is not claimed here."
            ),
            "summary": {
                "file_count": len(sorted_trees),
                "truncation": _truncation(returned=len(results), total=len(sorted_trees)),
            },
            "effective_defines": {key: value for key, value in bundle.project.defines},
            "files": results,
        }
    )


def _base_summary(bundle: AnalysisBundle) -> dict[str, Any]:
    diagnostics = bundle.compilation.getAllDiagnostics()
    severity_counts = Counter(
        _serialize_diagnostic(bundle, diagnostic)["severity"] for diagnostic in diagnostics
    )
    return {
        "file_count": len(bundle.project.files),
        "include_dir_count": len(bundle.project.include_dirs),
        "define_count": len(bundle.project.defines),
        "top_module_count": len(bundle.project.top_modules),
        "diagnostic_count": len(diagnostics),
        "diagnostic_severity_counts": dict(sorted(severity_counts.items())),
    }


def _project_status(bundle: AnalysisBundle) -> dict[str, Any]:
    diagnostics = list(bundle.compilation.getAllDiagnostics())
    error_count = sum(1 for diagnostic in diagnostics if diagnostic.isError())
    severity_counts: Counter[str] = Counter()
    unresolved_references = 0
    for diagnostic in diagnostics:
        severity = bundle.diagnostic_engine.getSeverity(
            diagnostic.code, diagnostic.location
        ).name.lower()
        severity_counts[severity] += 1
        code_text = str(diagnostic.code).lower()
        message = _format_diagnostic_message(bundle, diagnostic).lower()
        if any(
            marker in code_text or marker in message
            for marker in (
                "undeclared",
                "unresolved",
                "unknown module",
                "unknown type",
                "could not find",
            )
        ):
            unresolved_references += 1

    if unresolved_references:
        status = "incomplete"
    elif error_count:
        status = "degraded"
    else:
        status = "ok"

    return {
        "status": status,
        "diagnostic_count": len(diagnostics),
        "error_count": error_count,
        "warning_count": severity_counts.get("warning", 0),
        "unresolved_references": unresolved_references,
    }


def _design_unit_symbols(bundle: AnalysisBundle) -> list[Any]:
    return [*bundle.compilation.getDefinitions(), *bundle.compilation.getPackages()]


def _analysis_index(bundle: AnalysisBundle) -> AnalysisIndex:
    if bundle.index is None:
        bundle.index = _build_index(bundle)
    return bundle.index


def _build_index(bundle: AnalysisBundle) -> AnalysisIndex:
    """Build the warm-query index for a compiled project."""

    design_units = tuple(
        sorted(
            _design_unit_symbols(bundle),
            key=lambda item: (str(getattr(item, "name", "")), str(item.hierarchicalPath)),
        )
    )
    design_unit_records: list[dict[str, Any]] = []
    design_unit_symbols_by_key: dict[tuple[str, str], Any] = {}
    declarations: list[IndexedDeclaration] = []
    references: list[IndexedReference] = []
    instances: list[Any] = []
    instance_records_by_path: dict[str, dict[str, Any]] = {}
    children_by_parent: defaultdict[str | None, list[str]] = defaultdict(list)
    seen_declarations: set[tuple[str, str, str | None]] = set()
    seen_references: set[tuple[str, str, str | None, str | None]] = set()

    for symbol in design_units:
        record = _serialize_design_unit_record(bundle, symbol)
        if record is not None:
            design_unit_records.append(record)
            design_unit_symbols_by_key[(record["name"], record["hierarchical_path"])] = symbol
        _maybe_add_indexed_declaration(
            bundle=bundle,
            symbol=symbol,
            seen=seen_declarations,
            target=declarations,
        )

    def visit(symbol: Any) -> bool:
        kind = getattr(symbol, "kind", None)
        if kind is not None and kind.name == "Instance":
            path = str(symbol.hierarchicalPath)
            instances.append(symbol)
            instance_records_by_path[path] = _serialize_instance(bundle, symbol)
            parent = path.rsplit(".", 1)[0] if "." in path else None
            children_by_parent[parent].append(path)

        references.extend(
            _collect_reference_index_entries(
                bundle=bundle,
                symbol=symbol,
                seen=seen_references,
            )
        )

        if kind is not None and kind.name == "NamedValue":
            return True
        if getattr(symbol, "name", None):
            _maybe_add_indexed_declaration(
                bundle=bundle,
                symbol=symbol,
                seen=seen_declarations,
                target=declarations,
            )
        return True

    bundle.compilation.getRoot().visit(visit)

    sorted_children = {
        parent: tuple(sorted(child_paths)) for parent, child_paths in children_by_parent.items()
    }
    top_instance_paths = tuple(
        str(instance.hierarchicalPath) for instance in bundle.compilation.getRoot().topInstances
    )

    return AnalysisIndex(
        design_units=design_units,
        design_unit_records=tuple(design_unit_records),
        design_unit_symbols_by_key=design_unit_symbols_by_key,
        instances=tuple(instances),
        instance_records_by_path=instance_records_by_path,
        children_by_parent=sorted_children,
        top_instance_paths=top_instance_paths,
        declarations=tuple(declarations),
        references=tuple(references),
    )


def _serialize_diagnostic(bundle: AnalysisBundle, diagnostic: Any) -> dict[str, Any]:
    location = _serialize_location(bundle, diagnostic.location)
    severity = bundle.diagnostic_engine.getSeverity(diagnostic.code, diagnostic.location).name
    return {
        "code": str(diagnostic.code),
        "severity": severity.lower(),
        "message": _format_diagnostic_message(bundle, diagnostic),
        "args": [str(argument) for argument in diagnostic.args],
        "location": location,
        "line_excerpt": _line_excerpt(bundle, location),
        "is_error": bool(diagnostic.isError()),
    }


def _serialize_location(bundle: AnalysisBundle, location: Any) -> dict[str, Any] | None:
    if location is None:
        return None
    try:
        full_path = Path(bundle.source_manager.getFullPath(location.buffer)).resolve(strict=False)
    except Exception:
        return None
    if not full_path.exists():
        return None
    try:
        full_path.relative_to(bundle.project.project_root)
    except ValueError:
        return None
    return {
        "path": relative_path(bundle.project.project_root, full_path),
        "line": bundle.source_manager.getLineNumber(location),
        "column": bundle.source_manager.getColumnNumber(location),
    }


def _serialize_range_location(bundle: AnalysisBundle, source_range: Any) -> dict[str, Any] | None:
    location = _serialize_location(bundle, source_range.start)
    if location is None:
        return None
    location["end_line"] = bundle.source_manager.getLineNumber(source_range.end)
    location["end_column"] = bundle.source_manager.getColumnNumber(source_range.end)
    return location


def _line_excerpt(bundle: AnalysisBundle, location: dict[str, Any] | None) -> str | None:
    if location is None:
        return None
    path = bundle.project.project_root / str(location["path"])
    line_number = int(location["line"])
    return _read_line(Path(path), line_number)


def _read_line(path: Path, line_number: int) -> str | None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return None
    if line_number < 1 or line_number > len(lines):
        return None
    return lines[line_number - 1].rstrip()


def _read_leading_lines(path: Path, max_lines: int) -> str:
    if max_lines <= 0:
        return ""
    lines: list[str] = []
    try:
        with path.open(encoding="utf-8") as handle:
            for _ in range(max_lines):
                line = handle.readline()
                if not line:
                    break
                lines.append(line.rstrip("\n"))
    except FileNotFoundError:
        return ""
    return "\n".join(lines)


def _truncation(*, returned: int, total: int) -> dict[str, object]:
    return {
        "returned": returned,
        "total": total,
        "truncated": total > returned,
        "remaining": max(total - returned, 0),
    }


def _filter_indexed_outputs(
    entries: Iterable[IndexedDeclaration | IndexedReference],
    *,
    query: str,
    match_mode: MatchMode,
    max_items: int,
) -> tuple[list[dict[str, Any]], dict[str, object]]:
    limit = max(max_items, 0)
    total = 0
    outputs: list[dict[str, Any]] = []
    for entry in entries:
        if not _matches_text(query=query, match_mode=match_mode, candidates=entry.candidates):
            continue
        total += 1
        if len(outputs) < limit:
            outputs.append(entry.output)
    return outputs, _truncation(returned=len(outputs), total=total)


def _format_diagnostic_message(bundle: AnalysisBundle, diagnostic: Any) -> str:
    message = bundle.diagnostic_engine.getMessage(diagnostic.code)
    arguments = [str(argument) for argument in diagnostic.args]
    try:
        return message.format(*arguments)
    except (IndexError, KeyError, ValueError):
        replacements = iter(arguments)
        return re.sub(r"(?<!\{)\{\}(?!\})", lambda _: next(replacements, "{}"), message)


def _serialize_design_unit_record(bundle: AnalysisBundle, symbol: Any) -> dict[str, Any] | None:
    location = _serialize_location(bundle, symbol.location)
    if location is None:
        return None
    return {
        "name": symbol.name,
        "kind": getattr(getattr(symbol, "definitionKind", None), "name", symbol.kind.name),
        "symbol_kind": symbol.kind.name,
        "hierarchical_path": str(symbol.hierarchicalPath),
        "lexical_path": str(symbol.lexicalPath),
        "instance_count": getattr(symbol, "instanceCount", None),
        "location": location,
    }


def _tracked_paths(project: ProjectConfig, source_manager: Any) -> tuple[Path, ...]:
    tracked: set[Path] = set(project.files) | set(project.filelists)
    for buffer_id in source_manager.getAllBuffers():
        full_path = Path(source_manager.getFullPath(buffer_id)).resolve(strict=False)
        if full_path == Path(".") or not full_path.exists():
            continue
        try:
            full_path.relative_to(project.project_root)
        except ValueError:
            continue
        tracked.add(full_path)
    return tuple(sorted(tracked))


def _collect_instances(bundle: AnalysisBundle) -> list[Any]:
    instances: list[Any] = []

    def visit(symbol: Any) -> bool:
        if getattr(symbol, "kind", None) and symbol.kind.name == "Instance":
            instances.append(symbol)
        return True

    bundle.compilation.getRoot().visit(visit)
    return instances


def _serialize_instance(bundle: AnalysisBundle, instance: Any) -> dict[str, Any]:
    return {
        "name": instance.name,
        "definition": getattr(getattr(instance, "definition", None), "name", None),
        "hierarchical_path": str(instance.hierarchicalPath),
        "location": _serialize_location(bundle, instance.location),
        "port_connections": [
            {
                "port": connection.port.name,
                "expression_kind": connection.expression.kind.name,
                "snippet": _source_snippet(bundle, connection.expression.sourceRange),
                "symbol": getattr(getattr(connection.expression, "symbol", None), "name", None),
            }
            for connection in instance.portConnections
        ],
    }


def _source_snippet(bundle: AnalysisBundle, source_range: Any, *, limit: int = 80) -> str | None:
    try:
        text = bundle.source_manager.getSourceText(source_range.start.buffer)
    except Exception:
        return None
    snippet = text[source_range.start.offset : source_range.end.offset].replace("\x00", "").strip()
    return snippet[:limit] if snippet else None


def _matches_symbol(query: str, match_mode: MatchMode, symbol: Any) -> bool:
    return _matches_text(query=query, match_mode=match_mode, candidates=_symbol_candidates(symbol))


def _symbol_candidates(symbol: Any) -> tuple[str, ...]:
    return _candidate_tuple(
        (
            getattr(symbol, "name", ""),
            str(getattr(symbol, "hierarchicalPath", "")),
            str(getattr(symbol, "lexicalPath", "")),
        )
    )


def _candidate_tuple(candidates: Iterable[object | None]) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate is None:
            continue
        text = str(candidate)
        if not text or text in seen:
            continue
        ordered.append(text)
        seen.add(text)
    return tuple(ordered)


def _matches_text(query: str, match_mode: MatchMode, candidates: Any) -> bool:
    query_lower = query.lower()
    for candidate in candidates:
        if candidate is None:
            continue
        candidate_lower = candidate.lower()
        if match_mode == "exact" and candidate_lower == query_lower:
            return True
        if match_mode == "contains" and query_lower in candidate_lower:
            return True
        if match_mode == "startswith" and candidate_lower.startswith(query_lower):
            return True
    return False


def _leaf_type_name(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip()
    if "::" in cleaned:
        cleaned = cleaned.rsplit("::", 1)[-1]
    if "." in cleaned:
        cleaned = cleaned.rsplit(".", 1)[-1]
    cleaned = cleaned.strip()
    return cleaned or None


def _collect_reference_index_entries(
    *,
    bundle: AnalysisBundle,
    symbol: Any,
    seen: set[tuple[str, str, str | None, str | None]],
) -> list[IndexedReference]:
    entries: list[IndexedReference] = []
    symbol_type_name = type(symbol).__name__

    if symbol_type_name == "NamedValueExpression" and getattr(symbol, "symbol", None):
        referenced_symbol = symbol.symbol
        entry = _make_reference_index_entry(
            bundle=bundle,
            source_kind="named_value",
            target_symbol=referenced_symbol,
            location=_serialize_range_location(bundle, symbol.sourceRange),
            snippet=_source_snippet(bundle, symbol.sourceRange),
            candidates=_symbol_candidates(referenced_symbol),
            seen=seen,
        )
        if entry is not None:
            entries.append(entry)

    if symbol_type_name == "WildcardImportSymbol":
        package_name = getattr(symbol, "packageName", None)
        target_symbol = getattr(symbol, "package", None) or symbol
        entry = _make_reference_index_entry(
            bundle=bundle,
            source_kind="package_import",
            target_symbol=target_symbol,
            location=_serialize_location(bundle, getattr(symbol, "location", None)),
            snippet=_source_snippet(bundle, getattr(symbol.syntax, "sourceRange", None)),
            candidates=(*_symbol_candidates(target_symbol), package_name),
            seen=seen,
        )
        if entry is not None:
            entries.append(entry)

    if symbol_type_name == "InstanceSymbol":
        definition = getattr(symbol, "definition", None)
        if definition is not None:
            location = _serialize_location(bundle, getattr(symbol, "location", None))
            entry = _make_reference_index_entry(
                bundle=bundle,
                source_kind="instance_definition",
                target_symbol=definition,
                location=location,
                snippet=_line_excerpt(bundle, location),
                candidates=_symbol_candidates(definition),
                seen=seen,
            )
            if entry is not None:
                entries.append(entry)

    declared_type = getattr(symbol, "declaredType", None)
    declared_type_syntax = getattr(declared_type, "typeSyntax", None)
    if (
        symbol_type_name in {"VariableSymbol", "PortSymbol", "TypeAliasType"}
        and declared_type_syntax
    ):
        type_text = str(getattr(symbol, "type", "")) or str(
            getattr(getattr(declared_type, "type", None), "canonicalType", "")
        )
        declared_type_text = _source_snippet(bundle, declared_type_syntax.sourceRange)
        entry = _make_reference_index_entry(
            bundle=bundle,
            source_kind="declared_type",
            target_symbol=symbol,
            location=_serialize_location(bundle, getattr(symbol, "location", None)),
            snippet=_source_snippet(bundle, declared_type_syntax.sourceRange),
            candidates=(
                *_symbol_candidates(symbol),
                type_text,
                declared_type_text,
                _leaf_type_name(type_text),
                _leaf_type_name(declared_type_text),
            ),
            seen=seen,
        )
        if entry is not None:
            entries.append(entry)

    return entries


def _make_reference_index_entry(
    *,
    bundle: AnalysisBundle,
    source_kind: str,
    target_symbol: Any,
    location: dict[str, Any] | None,
    snippet: str | None,
    candidates: Iterable[object | None],
    seen: set[tuple[str, str, str | None, str | None]],
) -> IndexedReference | None:
    output = _make_reference_hit(
        bundle=bundle,
        source_kind=source_kind,
        target_symbol=target_symbol,
        location=location,
        snippet=snippet,
        seen=seen,
    )
    if output is None:
        return None
    return IndexedReference(
        candidates=_candidate_tuple(
            (
                *candidates,
                output.get("name"),
                output.get("target_kind"),
                output.get("target_path"),
                output.get("reference_kind"),
            )
        ),
        output=output,
    )


def _make_reference_hit(
    *,
    bundle: AnalysisBundle,
    source_kind: str,
    target_symbol: Any,
    location: dict[str, Any] | None,
    snippet: str | None,
    seen: set[tuple[str, str, str | None, str | None]],
) -> dict[str, Any] | None:
    target_path = str(
        getattr(target_symbol, "hierarchicalPath", getattr(target_symbol, "name", ""))
    )
    target_kind = getattr(target_symbol, "kind", None)
    key = (
        source_kind,
        target_path,
        location["path"] if location else None,
        snippet,
    )
    if key in seen:
        return None
    seen.add(key)
    return {
        "name": getattr(target_symbol, "name", None),
        "target_kind": target_kind.name
        if target_kind is not None
        else type(target_symbol).__name__,
        "target_path": target_path,
        "reference_kind": source_kind,
        "location": location,
        "snippet": snippet,
    }


def _maybe_add_indexed_declaration(
    *,
    bundle: AnalysisBundle,
    symbol: Any,
    seen: set[tuple[str, str, str | None]],
    target: list[IndexedDeclaration],
) -> None:
    location = _serialize_location(bundle, getattr(symbol, "location", None))
    kind = getattr(symbol, "kind", None)
    kind_name = kind.name if kind is not None else type(symbol).__name__
    path = str(getattr(symbol, "hierarchicalPath", getattr(symbol, "name", "")))
    key = (kind_name, path, location["path"] if location else None)
    if key in seen:
        return
    seen.add(key)
    output = {
        "name": getattr(symbol, "name", None),
        "kind": kind_name,
        "hierarchical_path": path,
        "lexical_path": str(getattr(symbol, "lexicalPath", getattr(symbol, "name", ""))),
        "location": location,
    }
    target.append(IndexedDeclaration(candidates=_symbol_candidates(symbol), output=output))


def _collect_member_kinds(members: list[dict[str, Any]]) -> list[str]:
    kinds: list[str] = []
    for member in members:
        kind = member.get("kind")
        if isinstance(kind, str):
            kinds.append(kind)
    return kinds


def _extract_ports(syntax_json: dict[str, Any]) -> list[dict[str, Any]]:
    header = syntax_json.get("header", {})
    port_list = header.get("ports", {})
    ports: list[dict[str, Any]] = []
    for port in port_list.get("ports", []):
        if not isinstance(port, dict):
            continue
        if port.get("kind") not in {"ImplicitAnsiPort", "ExplicitAnsiPort"}:
            continue
        declarator = port.get("declarator", {})
        header_json = port.get("header", {})
        name = (
            declarator.get("name", {}).get("text")
            or port.get("name", {}).get("text")
            or port.get("externalName", {}).get("text")
        )
        if not name:
            continue
        direction = header_json.get("direction", {}).get("text")
        data_type = header_json.get("dataType", {}).get("kind")
        ports.append(
            {
                "name": name,
                "direction": direction,
                "data_type_kind": data_type,
            }
        )
    return ports


def _extract_child_instances(syntax_json: dict[str, Any]) -> list[dict[str, Any]]:
    instances: list[dict[str, Any]] = []
    for member in syntax_json.get("members", []):
        if not isinstance(member, dict) or member.get("kind") != "HierarchyInstantiation":
            continue
        definition_name = member.get("type", {}).get("text")
        for instance in member.get("instances", []):
            if not isinstance(instance, dict):
                continue
            instance_name = instance.get("decl", {}).get("name", {}).get("text")
            if instance_name:
                instances.append({"name": instance_name, "definition": definition_name})
    return instances


def _extract_declared_names(syntax_json: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for member in syntax_json.get("members", []):
        if not isinstance(member, dict):
            continue
        kind = member.get("kind")
        if kind == "DataDeclaration":
            for declarator in member.get("declarators", []):
                if isinstance(declarator, dict):
                    name = declarator.get("name", {}).get("text")
                    if name:
                        names.append(name)
        elif kind == "TypeAliasDeclaration":
            name = member.get("name", {}).get("text")
            if name:
                names.append(name)
    return names
