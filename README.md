# pyslang-mcp

`pyslang-mcp` is a planned open-source Model Context Protocol (MCP) server for
read-only, compiler-backed analysis of Verilog and SystemVerilog projects using
[`pyslang`](https://pypi.org/project/pyslang/).

The goal is to give AI clients a practical way to inspect HDL projects through
semantic analysis instead of raw text search. This project is intended to be a
semantic analysis MCP, not a simulator, synthesizer, waveform viewer, or code
generator.

## Status

This repository is still pre-implementation, but the initial research spike has
been completed.

- No release is published yet.
- No runnable MCP server exists in the repo yet.
- The MCP tool schemas are not frozen yet.
- The intended first transport is `stdio`.
- The server will enforce a strict read-only trust boundary.

Progress completed so far:

- repo created on GitHub
- implementation plan captured in [`pyslang-mcp-plan.md`](./pyslang-mcp-plan.md)
- contributor / agent handoff documented in [`AGENTS.md`](./AGENTS.md)
- local validation spike completed against `pyslang` and the stable Python MCP SDK

If you are evaluating or contributing early, read these first:

- [`AGENTS.md`](./AGENTS.md)
- [`pyslang-mcp-plan.md`](./pyslang-mcp-plan.md)

## Why This Project Exists

AI coding agents can already search HDL codebases as plain text, but that is a
weak substitute for compiler-backed understanding. `pyslang-mcp` is intended to
bridge that gap by exposing compact, structured answers about a local
Verilog/SystemVerilog project:

- what design units exist
- what diagnostics were produced
- how modules instantiate each other
- where a symbol is declared or referenced
- how preprocessing and filelists resolve in practice

The design emphasis is on token-efficient, stable JSON responses that can be
used by MCP clients without dumping full compiler internals or raw ASTs by
default.

## Research Validated So Far

The following behavior has already been validated locally and should guide the
first implementation:

- `pyslang` 10.0.0 installs and exposes usable Python bindings on Linux
- the stable MCP Python SDK target is the `v1.x` line, not the in-development
  `main` / v2 docs
- `SyntaxTree.fromFile`, `Compilation.addSyntaxTree`, diagnostics extraction,
  symbol traversal, and hierarchy traversal are all usable from Python
- include directory handling works
- semantic diagnostics work on broken HDL inputs
- hierarchy traversal works through `root.topInstances` plus `visit()`
- symbol references can be recovered from bound expressions

Known caveat:

- a clean, binding-level “full preprocessed text dump” API has not been fully
  validated yet, so `preprocess_files` should be implemented conservatively

## V1 Scope

The first usable release is planned to include:

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

## Non-Goals

Version 1 is explicitly not aiming to provide:

- simulation
- synthesis
- waveform viewing
- testbench generation
- RTL editing or refactoring
- remote code execution
- full IDE or language-server parity

## Design Principles

- Compiler-backed analysis through `pyslang`
- Official Python MCP SDK with `FastMCP`
- `stdio` transport first
- Strictly read-only filesystem interaction
- Explicit project roots or client-provided roots
- Compact, stable JSON outputs
- Output limits and truncation markers for large responses
- Clear error types for bad paths, parse failures, and unsupported queries
- Caching keyed by project configuration and file mtimes

## Planned Architecture

The current plan is to structure the project around a small analysis core and a
thin MCP layer:

```text
README.md
AGENTS.md
pyproject.toml
src/pyslang_mcp/__init__.py
src/pyslang_mcp/__main__.py
src/pyslang_mcp/server.py
src/pyslang_mcp/project_loader.py
src/pyslang_mcp/analysis.py
src/pyslang_mcp/serializers.py
src/pyslang_mcp/cache.py
src/pyslang_mcp/types.py
tests/
tests/fixtures/
examples/
```

Implementation should start with direct Python analysis functions, followed by
MCP tool exposure once the outputs are tested and stable.

## Roadmap

- `M0`: research spike and `pyslang` API validation
- `M1`: repo scaffold and locally runnable server
- `M2`: parsing, filelists, preprocessing, diagnostics
- `M3`: design-unit listing, hierarchy, symbol lookup
- `M4`: hardening, caching, schema freeze, docs
- `M5`: PyPI release, MCP registry publish, announcement

## Tooling Plan

- `uv` for packaging and local development
- `pytest` for tests
- `ruff` for linting and formatting
- `pyright` or `mypy` for static type checking
- GitHub Actions for CI and release automation
- PyPI trusted publishing for package releases

## Acceptance Criteria For The First Release

The first release should:

- install cleanly with `uvx` or `pip`
- analyze real multi-file SystemVerilog projects with include dirs and defines
- return stable JSON for diagnostics, design units, hierarchy, and symbol lookups
- fail clearly on malformed inputs and broken projects
- include fixture-backed CI coverage
- provide copy-paste client setup documentation

## Current Priorities

The next implementation tasks are:

1. scaffold `pyproject.toml` and `src/pyslang_mcp/`
2. implement `.f` filelist parsing and project loading
3. turn the validated `pyslang` probes into reusable analysis functions
4. define stable response schemas for diagnostics and semantic queries
5. build a representative fixture corpus and test suite

## References

- `pyslang`: <https://pypi.org/project/pyslang/>
- `slang`: <https://github.com/MikePopoloski/slang>
- Python MCP SDK: <https://github.com/modelcontextprotocol/python-sdk>
- MCP Registry: <https://github.com/modelcontextprotocol/registry>

## License

This repository is licensed under the terms in [`LICENSE`](./LICENSE).
