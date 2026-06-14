# `pyslang-mcp` Microarchitecture

This document describes the internal module layout of `pyslang-mcp` and how
the pieces cooperate on a single tool call. It is intentionally scoped to
the current early implementation — the public OSS MaaS and internal MaaS
directions are sketched separately in
[`../REMOTE_DEPLOYMENT.md`](../REMOTE_DEPLOYMENT.md).

## Module Map

Each node is one Python module inside `src/pyslang_mcp/` (or an external
dependency). Arrows are real import / call edges.

```mermaid
flowchart TD
    classDef entry fill:#1f3b57,stroke:#6fb1ff,color:#fff
    classDef transport fill:#254d2b,stroke:#6fd17d,color:#fff
    classDef schema fill:#4a2f57,stroke:#c28bdb,color:#fff
    classDef core fill:#4a3a1f,stroke:#f2b84b,color:#fff
    classDef infra fill:#1f4a4a,stroke:#6fd1d1,color:#fff
    classDef types fill:#333,stroke:#bbb,color:#fff
    classDef ext fill:#111,stroke:#888,color:#ddd,stroke-dasharray: 4 2
    classDef aux fill:#3a3a3a,stroke:#888,color:#eee

    subgraph CLI["CLI"]
        Main["__main__.py<br/>argparse<br/>--transport choice<br/>main(argv)"]
    end

    subgraph Transport["Transport / MCP wrapper"]
        Server["server.py<br/>FastMCP instance<br/>15 @mcp.tool defs<br/>/healthz custom route<br/>Annotated params + descriptions<br/>success_result / error_result / run_tool<br/>ToolInputError"]
        Auth["auth.py<br/>StaticBearerTokenVerifier<br/>simple internal HTTP bearer-token verifier"]
        Schemas["schemas.py<br/>Pydantic output models<br/>ToolErrorResult + ToolErrorDetail<br/>StrictModel (extra='forbid')<br/>HierarchyNode recursive rebuild"]
    end

    subgraph Core["Analysis core"]
        Analysis["analysis.py<br/>build_analysis / parse_summary<br/>filelist_summary<br/>get_diagnostics / summarize_diagnostics_by_code<br/>list_design_units / describe_design_unit / get_hierarchy<br/>find_symbol / find_member / get_assignments<br/>get_instance_connections / trace_connectivity<br/>dump_syntax_tree_summary / preprocess_files / get_project_summary<br/>symbol-walk visitors<br/>serialize_location / source_snippet"]
        Loader["project_loader.py<br/>resolve_project_root<br/>load_project_from_files / load_project_from_filelist<br/>_parse_filelist + _visit_filelist<br/>_strip_inline_comments (quote-aware)<br/>_normalize_path (relative_to-root guard)<br/>_normalize_defines / _normalize_top_modules<br/>ProjectLoadError / PathOutsideRootError"]
    end

    subgraph Infra["Infrastructure"]
        Cache["cache.py<br/>AnalysisCache<br/>OrderedDict LRU, max_entries=16<br/>sha256 of project_config_json<br/>mtime snapshot per tracked path<br/>DEFAULT_CACHE"]
        Serializers["serializers.py<br/>stabilize_json / limit_list<br/>relative_path / top_counts<br/>project_config_json / ensure_jsonable_paths"]
        Types["types.py<br/>ProjectConfig (frozen, slots)<br/>AnalysisBundle<br/>JsonValue"]
    end

    subgraph Aux["Auxiliary"]
        HdlEx["hdl_examples.py<br/>corpus loader (load_examples)<br/>pyslang validator<br/>Verilator --lint-only validator<br/>manifest coverage check"]
        Scripts["scripts/validate_hdl_examples.py<br/>thin CLI over hdl_examples"]
    end

    subgraph Ext["External"]
        FastMCP["mcp.server.fastmcp<br/>mcp.types"]
        Pyslang["pyslang<br/>SyntaxTree / Compilation<br/>SourceManager / Bag<br/>DiagnosticEngine<br/>PreprocessorOptions / CompilationOptions"]
        Pydantic["pydantic<br/>BaseModel / ConfigDict / Field"]
    end

    Main --> Server
    Server --> Auth
    Server --> Schemas
    Server --> Analysis
    Server --> Loader
    Server --> Cache
    Server --> Types
    Server --> FastMCP
    Schemas --> Pydantic

    Analysis --> Pyslang
    Analysis --> Serializers
    Analysis --> Types

    Loader --> Types

    Cache --> Serializers
    Cache --> Types

    Serializers --> Types

    HdlEx --> Analysis
    HdlEx --> Loader
    Scripts --> HdlEx

    class Main entry
    class Server,Auth,Schemas transport
    class Analysis,Loader core
    class Cache,Serializers infra
    class Types types
    class FastMCP,Pyslang,Pydantic ext
    class HdlEx,Scripts aux
```

## Tool-Call Sequence

What happens when a client invokes a tool. Diagnostics and load errors
become structured MCP tool errors; success paths return validated
Pydantic payloads in `structuredContent`.

```mermaid
sequenceDiagram
    autonumber
    participant C as MCP Client
    participant F as FastMCP (server.py)
    participant R as run_tool wrapper
    participant L as project_loader
    participant H as AnalysisCache
    participant A as analysis.py
    participant P as pyslang
    participant S as schemas.py

    C->>F: call_tool(name, args)
    F->>R: run_tool(ResultSchema, callback)
    R->>L: load_project_from_{files,filelist}
    L-->>R: ProjectConfig | ProjectLoadError
    alt path outside root / bad input
        R-->>F: error_result(code, message, hint, isError=True)
        F-->>C: CallToolResult(isError=True, structuredContent.error)
    else success
        R->>H: get_or_build(project, factory)
        alt cache hit
            H-->>R: AnalysisBundle (LRU touch)
        else cache miss
            H->>A: build_analysis(project)
            A->>P: SyntaxTree.fromFile / Compilation / elaborate
            P-->>A: compilation + syntax trees + diagnostic engine
            A-->>H: AnalysisBundle
            H-->>R: AnalysisBundle (sha256 + mtimes recorded)
        end
        R->>A: tool-specific query (get_hierarchy, find_symbol, ...)
        A-->>R: dict payload (stabilize_json + limit_list applied)
        R->>S: ResultSchema.model_validate(payload)
        S-->>R: validated model
        R-->>F: CallToolResult(content=TextContent, structuredContent={"result": ...})
        F-->>C: CallToolResult
    end
```

## Responsibility Matrix

| Module | Role | Depends on |
|---|---|---|
| `__main__.py` | CLI. Parses `--transport`, invokes `create_server().run(transport)`. | `server` |
| `server.py` | MCP surface. Registers fifteen read-only `@mcp.tool`s with `Annotated` input schemas, typed return schemas, a `/healthz` HTTP route, and a central `run_tool` wrapper that converts load / input errors into structured tool errors. | `analysis`, `project_loader`, `cache`, `schemas`, `types`, `auth`, `mcp.server.fastmcp` |
| `auth.py` | Simple static bearer-token verifier used by the internal MaaS HTTP path. This is not a replacement for company SSO in a broader team deployment. | `mcp.server.auth.provider` |
| `schemas.py` | Pydantic output models (one per tool) plus `ToolErrorResult`. `StrictModel` forbids extra keys; `HierarchyNode.model_rebuild()` enables recursive `children`. FastMCP reads these via `Annotated[CallToolResult, Result \| Error]`. | `pydantic` |
| `analysis.py` | pyslang-backed analysis functions. Builds `Compilation`, elaborates, and extracts diagnostics, design units, hierarchy, symbols, assignments, instance connections, bounded structural connectivity, syntax-tree summaries, and preprocessing metadata. Everything flows through `stabilize_json` + `limit_list`. | `pyslang`, `serializers`, `types` |
| `project_loader.py` | Normalizes and safety-checks project inputs. Resolves project roots, expands nested `.f` filelists (`-f`, `-F`, `+incdir+`, `-I`, `+define+`), records unsupported tokens, and enforces `relative_to(root)` on every path. | `types` |
| `cache.py` | Bounded LRU analysis cache. Key = sha256 of normalized `project_config_json`; invalidation = tuple of `(posix_path, mtime_ns)` over `tracked_paths`. `max_entries=16`. | `serializers`, `types` |
| `serializers.py` | Stable JSON helpers: `stabilize_json` (deep sort), `limit_list` (truncation metadata), `relative_path`, `top_counts`, `project_config_json`, `ensure_jsonable_paths`. | `types` |
| `types.py` | Shared internal types. `ProjectConfig` is frozen and `slots=True` (hashable + safe cache key). `AnalysisBundle` holds the pyslang state. | (stdlib) |
| `hdl_examples.py` | Corpus loader and validators used by the HDL smoke tests and the standalone script. Validates every manifest entry with both pyslang and `verilator --lint-only`. | `analysis`, `project_loader` |
| `scripts/validate_hdl_examples.py` | Thin CLI over `hdl_examples`. `--smoke-only` selects the CI subset. | `pyslang_mcp.hdl_examples` |

## Invariants

- Every tool is read-only (`READ_ONLY_ANNOTATIONS` at `server.py:45-50`).
- Every path the user supplies is rewritten with `Path.resolve()` and
  then checked with `Path.relative_to(project_root)` before any read
  (`project_loader.py:250-273`).
- All list-shaped outputs carry `{returned, total, truncated, remaining}`
  (`serializers.py:25-35`).
- All dict outputs are run through `stabilize_json` so ordering is
  deterministic across runs and across Python hash-seed changes.
- Cache keys include the normalized `ProjectConfig`; entries invalidate
  on any tracked-path mtime change.
- `preprocess_files` is advertised as `mode: "summary_only"` — never
  claim full preprocessor fidelity.

## Extension Points

- **New tool.** Add a Pydantic result model in `schemas.py`, implement
  the query in `analysis.py`, register an `@mcp.tool` in `server.py`
  with `Annotated` args + `run_tool` wrapper. The current Verilog
  analysis extensions include member lookup, assignment lookup,
  instance-connection summaries, bounded connectivity tracing, and
  diagnostic grouping by code.
- **New filelist directive.** Extend the token handlers in
  `project_loader._visit_filelist`; unknown tokens already land in
  `unsupported_filelist_entries`, so tightening coverage there is the
  safest first step.
- **Hosted transport.** Add an authenticated HTTP entry path alongside
  `__main__` (or a new `transport_http.py`), reuse `analysis` / `cache`
  / `project_loader` as-is. See `REMOTE_DEPLOYMENT.md` for the public OSS
  MaaS and self-hosted internal MaaS split.
- **Persistent cache.** The `AnalysisCache` interface is intentionally
  small (`get_or_build`, `clear`, `__len__`). A redis- or disk-backed
  implementation can swap in without touching the tool layer.
