"""Core pyslang-backed analysis functions."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
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
from .types import AnalysisBundle, ProjectConfig

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
    return AnalysisBundle(
        project=project,
        source_manager=source_manager,
        bag=bag,
        compilation=compilation,
        syntax_trees=syntax_trees,
        diagnostic_engine=DiagnosticEngine(source_manager),
        tracked_paths=tracked_paths,
    )


def parse_summary(bundle: AnalysisBundle) -> dict[str, Any]:
    """Return a concise parse summary for explicit file mode."""

    return stabilize_json(
        {
            "project": project_config_json(bundle.project),
            "parse": _base_summary(bundle),
        }
    )


def filelist_summary(bundle: AnalysisBundle) -> dict[str, Any]:
    """Return a concise parse summary for filelist mode."""

    return stabilize_json(
        {
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

    diagnostics = [
        _serialize_diagnostic(bundle, diagnostic)
        for diagnostic in bundle.compilation.getAllDiagnostics()
    ]
    diagnostics_json, truncation = limit_list(diagnostics, max_items=max_items)
    severity_counts = Counter(
        str(entry["severity"]).lower() for entry in diagnostics if entry.get("severity")
    )
    return stabilize_json(
        {
            "project_root": bundle.project.project_root.as_posix(),
            "summary": {
                "total": len(diagnostics),
                "severity_counts": dict(sorted(severity_counts.items())),
                "truncation": truncation,
            },
            "diagnostics": diagnostics_json,
        }
    )


def list_design_units(bundle: AnalysisBundle, *, max_items: int = 200) -> dict[str, Any]:
    """List project-local modules, interfaces, and packages."""

    units = [
        unit
        for unit in (
            _serialize_design_unit_record(bundle, symbol)
            for symbol in sorted(_design_unit_symbols(bundle), key=lambda item: item.name)
        )
        if unit is not None
    ]

    units_json, truncation = limit_list(units, max_items=max_items)
    type_counts = Counter(str(unit["kind"]) for unit in units)
    return stabilize_json(
        {
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

    local_records = [
        unit
        for unit in (
            _serialize_design_unit_record(bundle, symbol)
            for symbol in sorted(_design_unit_symbols(bundle), key=lambda item: item.name)
        )
        if unit is not None
    ]
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
                "query": name,
                "found": False,
                "ambiguous": len(exact_matches) > 1,
                "candidates": exact_matches or suggestions,
                "design_unit": None,
            }
        )

    selected_path = str(exact_matches[0]["hierarchical_path"])
    symbol = next(
        unit
        for unit in _design_unit_symbols(bundle)
        if unit.name == name and str(unit.hierarchicalPath) == selected_path
    )
    syntax_json = json.loads(symbol.syntax.to_json())
    member_counts = Counter(_collect_member_kinds(syntax_json.get("members", [])))
    description = {
        "query": name,
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
    return stabilize_json(description)


def get_hierarchy(
    bundle: AnalysisBundle,
    *,
    max_depth: int = 8,
    max_children: int = 100,
) -> dict[str, Any]:
    """Return the elaborated instance hierarchy from `root.topInstances`."""

    instance_map: dict[str, Any] = {}
    children_map: defaultdict[str | None, list[str]] = defaultdict(list)
    for instance in _collect_instances(bundle):
        path = str(instance.hierarchicalPath)
        instance_map[path] = instance
        parent = path.rsplit(".", 1)[0] if "." in path else None
        children_map[parent].append(path)

    for values in children_map.values():
        values.sort()

    def build_node(path: str, depth: int) -> dict[str, Any]:
        instance = instance_map[path]
        child_paths = children_map.get(path, [])
        node = _serialize_instance(bundle, instance)
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

    top_paths = [
        str(instance.hierarchicalPath) for instance in bundle.compilation.getRoot().topInstances
    ]
    hierarchy = [build_node(path, depth=1) for path in top_paths if path in instance_map]
    return stabilize_json(
        {
            "summary": {
                "top_instances": [node["hierarchical_path"] for node in hierarchy],
                "total_instances": len(instance_map),
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

    declarations: list[dict[str, Any]] = []
    references: list[dict[str, Any]] = []
    seen_declarations: set[tuple[str, str, str | None]] = set()
    seen_references: set[tuple[str, str, str | None, str | None]] = set()

    for symbol in _design_unit_symbols(bundle):
        _maybe_add_declaration(
            bundle=bundle,
            symbol=symbol,
            query=query,
            match_mode=match_mode,
            seen=seen_declarations,
            target=declarations,
        )

    def visit(symbol: Any) -> bool:
        if include_references:
            references.extend(
                _collect_reference_hits(
                    bundle=bundle,
                    symbol=symbol,
                    query=query,
                    match_mode=match_mode,
                    seen=seen_references,
                )
            )
        if getattr(symbol, "kind", None) and symbol.kind.name == "NamedValue":
            return True
        if getattr(symbol, "name", None):
            _maybe_add_declaration(
                bundle=bundle,
                symbol=symbol,
                query=query,
                match_mode=match_mode,
                seen=seen_declarations,
                target=declarations,
            )
        return True

    bundle.compilation.getRoot().visit(visit)
    limited_declarations, decl_truncation = limit_list(declarations, max_items=max_results)
    limited_references, ref_truncation = limit_list(references, max_items=max_results)
    return stabilize_json(
        {
            "query": query,
            "match_mode": match_mode,
            "declarations": limited_declarations,
            "references": limited_references,
            "summary": {
                "declaration_count": len(declarations),
                "reference_count": len(references),
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

    file_summaries: list[dict[str, Any]] = []
    for file_path, tree in sorted(bundle.syntax_trees.items()):
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

    limited_files, truncation = limit_list(file_summaries, max_items=max_files)
    return stabilize_json(
        {
            "summary": {
                "file_count": len(file_summaries),
                "truncation": truncation,
            },
            "files": limited_files,
        }
    )


def preprocess_files(
    bundle: AnalysisBundle,
    *,
    max_files: int = 50,
    max_excerpt_lines: int = 12,
) -> dict[str, Any]:
    """Return conservative preprocessing metadata and source excerpts."""

    results: list[dict[str, Any]] = []
    for file_path, tree in sorted(bundle.syntax_trees.items()):
        source_text = file_path.read_text(encoding="utf-8")
        excerpt = "\n".join(source_text.splitlines()[:max_excerpt_lines])
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

    limited_results, truncation = limit_list(results, max_items=max_files)
    return stabilize_json(
        {
            "mode": "summary_only",
            "note": (
                "This tool returns preprocessing metadata and source excerpts. "
                "A full standalone preprocessed text stream is not claimed here."
            ),
            "summary": {
                "file_count": len(results),
                "truncation": truncation,
            },
            "effective_defines": {key: value for key, value in bundle.project.defines},
            "files": limited_results,
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


def _design_unit_symbols(bundle: AnalysisBundle) -> list[Any]:
    return [*bundle.compilation.getDefinitions(), *bundle.compilation.getPackages()]


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
    candidates = {
        getattr(symbol, "name", ""),
        str(getattr(symbol, "hierarchicalPath", "")),
        str(getattr(symbol, "lexicalPath", "")),
    }
    return _matches_text(query=query, match_mode=match_mode, candidates=candidates)


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


def _collect_reference_hits(
    *,
    bundle: AnalysisBundle,
    symbol: Any,
    query: str,
    match_mode: MatchMode,
    seen: set[tuple[str, str, str | None, str | None]],
) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    symbol_type_name = type(symbol).__name__

    if symbol_type_name == "NamedValueExpression" and getattr(symbol, "symbol", None):
        referenced_symbol = symbol.symbol
        if _matches_symbol(query=query, match_mode=match_mode, symbol=referenced_symbol):
            hit = _make_reference_hit(
                bundle=bundle,
                source_kind="named_value",
                target_symbol=referenced_symbol,
                location=_serialize_range_location(bundle, symbol.sourceRange),
                snippet=_source_snippet(bundle, symbol.sourceRange),
                seen=seen,
            )
            if hit is not None:
                hits.append(hit)

    if symbol_type_name == "WildcardImportSymbol":
        package_name = getattr(symbol, "packageName", None)
        if isinstance(package_name, str) and _matches_text(
            query=query, match_mode=match_mode, candidates={package_name}
        ):
            hit = _make_reference_hit(
                bundle=bundle,
                source_kind="package_import",
                target_symbol=getattr(symbol, "package", None) or symbol,
                location=_serialize_location(bundle, getattr(symbol, "location", None)),
                snippet=_source_snippet(bundle, getattr(symbol.syntax, "sourceRange", None)),
                seen=seen,
            )
            if hit is not None:
                hits.append(hit)

    if symbol_type_name == "InstanceSymbol":
        definition = getattr(symbol, "definition", None)
        if definition is not None and _matches_symbol(
            query=query, match_mode=match_mode, symbol=definition
        ):
            location = _serialize_location(bundle, getattr(symbol, "location", None))
            hit = _make_reference_hit(
                bundle=bundle,
                source_kind="instance_definition",
                target_symbol=definition,
                location=location,
                snippet=_line_excerpt(bundle, location),
                seen=seen,
            )
            if hit is not None:
                hits.append(hit)

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
        candidates = {
            type_text,
            declared_type_text,
            _leaf_type_name(type_text),
            _leaf_type_name(declared_type_text),
        }
        if _matches_text(query=query, match_mode=match_mode, candidates=candidates):
            hit = _make_reference_hit(
                bundle=bundle,
                source_kind="declared_type",
                target_symbol=symbol,
                location=_serialize_location(bundle, getattr(symbol, "location", None)),
                snippet=_source_snippet(bundle, declared_type_syntax.sourceRange),
                seen=seen,
            )
            if hit is not None:
                hits.append(hit)

    return hits


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


def _maybe_add_declaration(
    *,
    bundle: AnalysisBundle,
    symbol: Any,
    query: str,
    match_mode: MatchMode,
    seen: set[tuple[str, str, str | None]],
    target: list[dict[str, Any]],
) -> None:
    if not _matches_symbol(query=query, match_mode=match_mode, symbol=symbol):
        return
    location = _serialize_location(bundle, getattr(symbol, "location", None))
    path = str(getattr(symbol, "hierarchicalPath", getattr(symbol, "name", "")))
    key = (symbol.kind.name, path, location["path"] if location else None)
    if key in seen:
        return
    seen.add(key)
    target.append(
        {
            "name": getattr(symbol, "name", None),
            "kind": symbol.kind.name,
            "hierarchical_path": path,
            "lexical_path": str(getattr(symbol, "lexicalPath", getattr(symbol, "name", ""))),
            "location": location,
        }
    )


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
