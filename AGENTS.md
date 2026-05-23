# AGENTS.md

This file is the handoff document for any AI agent or contributor working in
this repository.

Read this first, then read [README.md](./README.md),
[pyslang-mcp-plan.md](./pyslang-mcp-plan.md), and
[REMOTE_DEPLOYMENT.md](./REMOTE_DEPLOYMENT.md).

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

As of 2026-05-18, this repo has moved past the documentation-only stage into a
PyPI-published early implementation. The source metadata is prepared for the
first non-pre-release package, `0.1.0`, so normal installs use
`pip install pyslang-mcp`.

What exists:

- `LICENSE`
- `README.md`
- `pyslang-mcp-plan.md`
- this `AGENTS.md`
- `pyproject.toml`
- `src/pyslang_mcp/`
- `tests/` with fixture-backed coverage
- `.github/workflows/ci.yml`
- `.github/workflows/release.yml`
- `REMOTE_DEPLOYMENT.md`
- `Dockerfile`
- `deploy/internal/docker-compose.yml`
- `deploy/internal/systemd/pyslang-mcp.service.example`
- `docs/internal-maas-quickstart.md`
- PyPI package `pyslang-mcp`
- MCP Registry entry `io.github.ariklapid/pyslang-mcp`
- a local `.venv/` used for research and validation on this machine only

What does not exist yet:

- copy-paste client configuration examples for multiple MCP clients
- production MaaS hardening for broad internal team use, including SSO,
  multi-workspace routing, Kubernetes manifests, reverse-proxy examples, and
  source-safe metrics

Do not describe this repo as broadly client-ready. A PyPI package and MCP
Registry entry exist, but the project is still early-stage.

## Product Definition

The intended V1 tools are:

- `pyslang_parse_files`
- `pyslang_parse_filelist`
- `pyslang_get_diagnostics`
- `pyslang_list_design_units`
- `pyslang_describe_design_unit`
- `pyslang_get_hierarchy`
- `pyslang_find_symbol`
- `pyslang_dump_syntax_tree_summary`
- `pyslang_preprocess_files`
- `pyslang_get_project_summary`

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

## Remote / MaaS Position

MaaS is planned as two distinct tracks:

- public OSS MaaS for public HDL repositories only. This may be useful for
  demos, education, and open-source hardware workflows, but it is not a
  suitable security boundary for proprietary RTL.
- internal MaaS for real corporate RTL work. Companies should run
  `pyslang-mcp` inside their own network, with their own repository access,
  auth, logging, storage, and policy controls.

Do not imply that the current experimental `streamable-http` mode is a complete
production hosted security boundary. The internal MaaS path wraps it with a
bearer token for single-server use; broader team use still needs company auth,
gatewaying, workspace routing, and audit controls.

## Progress Done So Far

The main completed work so far is planning, API validation, and a first
end-to-end local implementation.

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

### Implemented Server

The repository now contains:

- `FastMCP` server wiring in `src/pyslang_mcp/server.py`
- CLI entrypoint in `src/pyslang_mcp/__main__.py`
- project loader with root safety and `.f` parsing
- `pyslang` analysis core for diagnostics, units, hierarchy, symbol search, and
  syntax summaries
- in-memory cache keyed by project config plus tracked file mtimes
- fixture-backed unit, integration, and MCP-level tests
- CI on GitHub Actions for Ubuntu with Python 3.11 and 3.12
- package smoke CI from a built wheel
- manual PyPI Trusted Publishing workflow with release-gate tests
- PyPI package release line
- MCP Registry entry `io.github.ariklapid/pyslang-mcp`
- internal MaaS artifacts for a single internal server:
  - Dockerfile
  - Docker Compose config
  - bearer-token HTTP option
  - setup script
  - native Python fallback docs
  - quickstart docs

The implemented V1 tools match the intended tool list, with one important
honesty constraint:

- `pyslang_preprocess_files` returns preprocessing metadata plus source excerpts, not a
  claimed full standalone-preprocessor output stream

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

- `pyslang_preprocess_files` should be implemented carefully and honestly.
- It may need to return a preprocessing summary plus safe excerpts first.
- Do not promise full standalone-preprocessor parity until verified.

## What Still Needs To Be Built

The major local implementation pieces now exist. The main remaining work is:

- real client configuration examples and docs
- broader real-world fixture coverage
- schema hardening / freeze decisions
- more filelist compatibility coverage
- platform validation beyond current Linux-focused testing
- production hardening for internal MaaS beyond the current single-server
  bring-up path
- public OSS MaaS threat model before any hosted public endpoint

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

The first public release should meet these standards:

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
- Do not promise `pyslang_preprocess_files` fidelity beyond what is actually validated.

## Next Steps For The Next Agent

If you are picking this up fresh, do this next:

1. Add more real-world fixtures, especially nested filelists, additional
   include-dir patterns, and broken multi-file projects.
2. Harden and document filelist compatibility boundaries.
3. Add client setup examples for local `stdio` use.
4. Keep PyPI install verification in the release checklist, especially
   `pip install pyslang-mcp` from a fresh environment.
5. Keep README and this file aligned with the true implementation status.

## Working Style

- Prefer small, testable analysis functions before MCP wrappers.
- Preserve strict separation between core analysis and transport concerns.
- Be explicit about trust boundaries and unsupported cases.
- Keep documentation technically honest.
- If you validate new `pyslang` behavior, write it down here or in repo docs.

## Skill And Eval Validation

CI intentionally runs only a lean, deterministic `pyslang-verilog-context`
smoke subset. It must not require real LLM access.

Contributors must run the full local eval validation before opening a PR.
Agents must also run it before commit or push when either of these changes:

- any semantic, wording, or content change to
  `skills/pyslang-verilog-context/SKILL.md`
- any added or revised Verilog/SystemVerilog example, fixture, filelist,
  include, or eval prompt that affects the skill corpus

Use all available local Verilog examples and evals, not just the CI smoke
subset:

```bash
./.venv/bin/python scripts/validate_hdl_examples.py
./.venv/bin/python skills/pyslang-verilog-context/scripts/validate_eval_fixtures.py
./.venv/bin/python skills/pyslang-verilog-context/scripts/run_comparison_evals.py
./.venv/bin/python scripts/run_mcp_comparison.py --output-dir reports/mcp_comparison_comprehensive_$(date +%Y%m%d)
./.venv/bin/python reports/real_examples_75/run_real75_comparison.py
./.venv/bin/python -m py_compile reports/real_examples_75/run_real75_comparison.py
```

If a full local eval cannot be run, document the reason and treat the result as
not fully validated.
