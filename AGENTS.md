# AGENTS.md

This file is the handoff document for any AI agent or contributor working in
this repository.

Read this first, then read [README.md](./README.md) and
[pyslang-mcp-plan.md](./pyslang-mcp-plan.md).

## Mission

Build a professional, open-source MCP server that gives AI systems
compiler-backed, read-only understanding of Verilog and SystemVerilog projects
through `pyslang`.

The server should be useful to:

- AI coding agents
- LLM-powered IDE tools
- workflow / skill systems
- automation flows that need HDL context

The product is a semantic analysis MCP, not an EDA runtime. Keep the scope
tight and technically honest.

## Current Repo Reality

As of 2026-04-18, this repo is still documentation-first.

What exists:

- `LICENSE`
- `README.md`
- `pyslang-mcp-plan.md`
- this `AGENTS.md`
- a local `.venv/` used for research spikes in this machine only

What does not exist yet:

- `pyproject.toml`
- `src/pyslang_mcp/`
- tests
- CI workflows
- publish automation
- a runnable MCP server

Do not describe this repo as implemented, released, or client-ready. It is not
there yet.

## Product Definition

The intended V1 tools are:

- `parse_files`
- `parse_filelist`
- `get_diagnostics`
- `list_design_units`
- `describe_design_unit`
- `get_hierarchy`
- `find_symbol`
- `dump_syntax_tree_summary`
- `preprocess_files`
- `get_project_summary`

V1 non-goals:

- simulation
- synthesis
- waveform viewing
- testbench generation
- RTL editing or refactoring
- remote code execution
- full IDE / language server parity

## Architecture Constraints

These are not optional unless the repo direction is explicitly changed.

- Use the official Python MCP SDK with `FastMCP`.
- Use `stdio` transport first.
- Keep the server strictly read-only.
- Require explicit project roots or clearly client-provided roots.
- Return compact, stable JSON outputs.
- Add output limits and truncation markers early.
- Cache by project config plus file mtimes.
- Prefer a small analysis core with a thin MCP wrapper.

## Progress Done So Far

The main completed work so far is planning plus a real `pyslang` / MCP API
validation spike.

### Planning

- Repo created on GitHub.
- Initial README written.
- Full implementation plan copied into `pyslang-mcp-plan.md`.

### Local Validation Spike

The following was validated locally in a virtual environment on Python 3.12:

- `pyslang` 10.0.0 installs cleanly on Linux.
- stable Python MCP SDK is the `v1.x` line, not the `main` / v2 pre-alpha docs.
- `mcp` 1.27.0 provides `FastMCP.run("stdio")`, `@mcp.tool()`, and direct
  `call_tool()` testing hooks.

#### `pyslang` APIs confirmed usable

- `pyslang.SyntaxTree.fromFile(path, sourceManager?, bag?)`
- `pyslang.Compilation()`
- `Compilation.addSyntaxTree(tree)`
- `Compilation.getParseDiagnostics()`
- `Compilation.getSemanticDiagnostics()`
- `Compilation.getAllDiagnostics()`
- `Compilation.getDefinitions()`
- `Compilation.getPackages()`
- `Compilation.getRoot()`
- `RootSymbol.topInstances`
- `Symbol.visit(callback)`
- `DiagnosticEngine.reportAll(sourceManager, diagnostics)`
- `DiagnosticEngine.getMessage(code)`
- `DiagnosticEngine.getSeverity(code, location)`

#### Behavior validated with probe files

- single-file parse works
- multi-file package/import flow works
- include directory resolution works
- semantic diagnostics work for unresolved identifiers / types
- hierarchy traversal works through `root.topInstances` plus `visit()`
- instance port connections are available through `InstanceSymbol.portConnections`
- symbol references can be recovered from expressions such as
  `NamedValueExpression.symbol`
- syntax-tree walking works and is suitable for summary generation
- `tree.getIncludeDirectives()` returns useful include metadata

## Important `pyslang` Notes

These findings matter for the implementation.

### 1. Stable MCP SDK target

Use the stable MCP Python SDK behavior and docs, not the in-development `main`
branch docs. Until this project intentionally upgrades, assume v1.x semantics.

### 2. Macro / predefine quirk

`PreprocessorOptions.predefines` behaved correctly when assigned as a complete
list:

```python
pp.predefines = ["EXTRA_MACRO=1"]
```

Do not rely on mutating `pp.predefines.append(...)` before attaching the
options to a `Bag`; that behavior was inconsistent in local probing.

### 3. Include path handling

Include resolution worked with:

- `SourceManager.addUserDirectories(...)`
- `PreprocessorOptions.additionalIncludePaths = [...]`

Both should be supported cleanly by the project loader.

### 4. Top-module configuration

`CompilationOptions.topModules` expects a `set[str]`, not a list.

### 5. Preprocessed text caveat

No clean binding-level API has been validated yet for dumping a full, faithful
preprocessed file text stream in the exact shape users might expect.

Implication:

- `preprocess_files` should be implemented carefully and honestly.
- It may need to return a preprocessing summary plus safe excerpts first.
- Do not promise full standalone-preprocessor parity until verified.

## What Still Needs To Be Built

Everything below is still pending:

- package scaffold
- entrypoint and CLI
- project loader
- filelist parser
- analysis core
- serializers and schemas
- cache layer
- MCP tool registration
- fixtures
- unit tests
- integration tests
- MCP-level tests
- CI
- release automation

## Recommended Build Order

Do the work in this order unless a strong reason emerges to change it.

1. Add `pyproject.toml` and package scaffold under `src/pyslang_mcp/`.
2. Add `.gitignore` so `.venv/`, caches, and test artifacts are not committed.
3. Implement the project loader:
   - explicit root handling
   - file path normalization
   - include dirs
   - define handling
   - `.f` filelist parsing
4. Implement analysis functions without MCP first.
5. Freeze JSON response schemas.
6. Add the MCP tool layer with `FastMCP`.
7. Add caching and response truncation.
8. Add tests and fixture corpus.
9. Add docs, examples, CI, and packaging polish.

## Suggested Module Responsibilities

- `project_loader.py`
  - path resolution
  - file discovery
  - root safety checks
  - `.f` parsing
  - compilation configuration assembly

- `analysis.py`
  - syntax-tree loading
  - compilation creation
  - diagnostics extraction
  - design-unit listing
  - hierarchy walk
  - symbol search
  - project summary

- `serializers.py`
  - compact JSON formatting
  - output truncation
  - stable ordering
  - schema normalization

- `cache.py`
  - project-config hashing
  - mtime snapshotting
  - cache invalidation

- `server.py`
  - MCP server construction
  - tool definitions
  - top-level error mapping

## Quality Bar

The first alpha should meet these standards:

- installable with `uvx pyslang-mcp` or `pip install pyslang-mcp`
- safe read-only behavior
- useful on real multi-file SV projects
- stable JSON outputs
- clear failures on bad input
- fixture-backed tests
- copy-paste client setup docs

## Things Agents Must Not Do

- Do not claim simulation, synthesis, or waveform support.
- Do not silently read arbitrary paths outside declared project scope.
- Do not dump giant raw ASTs by default.
- Do not depend on MCP Python SDK `main` / v2 behavior unless intentionally
  upgrading the project.
- Do not commit the local `.venv/`.
- Do not promise `preprocess_files` fidelity beyond what is actually validated.

## Next Steps For The Next Agent

If you are picking this up fresh, do this next:

1. Create `.gitignore`.
2. Create `pyproject.toml`.
3. Scaffold `src/pyslang_mcp/` with:
   - `__init__.py`
   - `__main__.py`
   - `server.py`
   - `project_loader.py`
   - `analysis.py`
   - `serializers.py`
   - `cache.py`
   - `types.py`
4. Add tests and fixtures before exposing all MCP tools.
5. Keep README and this file aligned with the true implementation status.

## Working Style

- Prefer small, testable analysis functions before MCP wrappers.
- Preserve strict separation between core analysis and transport concerns.
- Be explicit about trust boundaries and unsupported cases.
- Keep documentation technically honest.
- If you validate new `pyslang` behavior, write it down here or in repo docs.
