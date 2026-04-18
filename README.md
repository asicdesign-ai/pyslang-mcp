# pyslang-mcp

`pyslang-mcp` is an alpha-quality, local-first Model Context Protocol server
for read-only, compiler-backed analysis of Verilog and SystemVerilog projects
using [`pyslang`](https://pypi.org/project/pyslang/).

The goal is narrow and explicit: give AI clients structured HDL project context
through real parsing and elaboration, not raw text search. This project is a
semantic analysis MCP, not a simulator, synthesizer, waveform viewer, or code
generator.

## Status

As of 2026-04-18, the repository now contains a runnable implementation:

- `pyproject.toml` packaging metadata
- a `FastMCP` server under `src/pyslang_mcp/`
- a `stdio` entrypoint via `python -m pyslang_mcp`
- fixture-backed tests for loader, analysis, and MCP `call_tool()` paths
- an Ubuntu GitHub Actions CI workflow

What is still not done:

- no PyPI release yet
- no MCP Registry publication yet
- no publish automation yet
- no claim of frozen long-term schemas yet
- no promise of full standalone preprocessor fidelity

## Implemented Tools

The current alpha implements these read-only tools:

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

## Guardrails

- strict project-root scoping; paths outside the declared root are rejected
- `stdio` transport first
- compact JSON responses instead of giant raw compiler dumps
- in-memory caching keyed by normalized project config plus tracked file mtimes
- conservative `preprocess_files` behavior that returns preprocessing metadata
  and excerpts, not a claimed full preprocessed text stream

## Current Filelist Support

The implemented `.f` parser intentionally supports a practical subset:

- raw source file entries
- nested filelists with `-f` and `-F`
- include directories with `+incdir+...` and `-I`
- macro defines with `+define+...`

Unsupported directives are reported back in `parse_filelist` output instead of
being silently ignored.

## Quickstart

Local development setup:

```bash
python -m venv .venv
./.venv/bin/pip install -e '.[dev]'
```

Run the server over `stdio`:

```bash
./.venv/bin/python -m pyslang_mcp
```

Or choose a transport explicitly:

```bash
./.venv/bin/python -m pyslang_mcp --transport stdio
```

## Development Commands

```bash
./.venv/bin/ruff format src tests
./.venv/bin/ruff check src tests
./.venv/bin/pyright
./.venv/bin/pytest -q
```

## Architecture

The implementation follows the original plan:

- `project_loader.py`
  - project-root validation
  - safe path normalization
  - filelist parsing
  - include-dir and define handling
- `analysis.py`
  - `pyslang` compilation setup
  - diagnostics extraction
  - design-unit listing and description
  - hierarchy traversal
  - symbol search
  - syntax and preprocessing summaries
- `serializers.py`
  - stable path rendering
  - truncation helpers
- `cache.py`
  - project-config hashing
  - tracked-file mtime invalidation
- `server.py`
  - thin `FastMCP` tool wrappers

## Known Limitations

- `preprocess_files` is summary-oriented and intentionally conservative.
- The filelist parser is a useful subset, not full simulator compatibility.
- Tool outputs are designed to be stable and compact, but they are still alpha.
- Packaging and registry publishing are still pending.

## Roadmap

- `M0`: research spike and `pyslang` API validation
- `M1`: repo scaffold and local runnable server
- `M2`: parsing, filelists, preprocessing, diagnostics
- `M3`: design-unit listing, hierarchy, symbol lookup
- `M4`: hardening, caching, schema freeze, docs
- `M5`: PyPI release, registry publish, announcement

The repository is now through `M3` in local implementation terms, but release
and publication work is still outstanding.

## References

- `pyslang`: <https://pypi.org/project/pyslang/>
- `slang`: <https://github.com/MikePopoloski/slang>
- Python MCP SDK: <https://github.com/modelcontextprotocol/python-sdk>
- MCP Registry: <https://github.com/modelcontextprotocol/registry>

## License

This repository is licensed under the Apache 2.0 terms in
[`LICENSE`](./LICENSE).
