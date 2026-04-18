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

## Local Client Setup

Today, the intended connection model is local `stdio`.

That means:

- the MCP server process runs on the same machine, VM, or dev container that
  contains the HDL checkout
- the MCP client launches `pyslang-mcp` as a child process
- tool calls use `project_root` paths that exist on that same filesystem

This is the same basic pattern used by many local MCP integrations, even when a
vendor also offers hosted connectors for other products.

### Generic `stdio` Client Configuration

Generic local client configuration:

```json
{
  "mcpServers": {
    "pyslang-mcp": {
      "command": "/path/to/python",
      "args": [
        "-m",
        "pyslang_mcp",
        "--transport",
        "stdio"
      ]
    }
  }
}
```

For a local checkout with the repository virtualenv, that usually means:

```json
{
  "mcpServers": {
    "pyslang-mcp": {
      "command": "/absolute/path/to/pyslang-mcp/.venv/bin/python",
      "args": [
        "-m",
        "pyslang_mcp",
        "--transport",
        "stdio"
      ]
    }
  }
}
```

### Local Install Options

Development checkout:

```bash
git clone https://github.com/asicdesign-ai/pyslang-mcp.git
cd pyslang-mcp
python -m venv .venv
./.venv/bin/pip install -e '.[dev]'
```

Then point the MCP client at:

- `command`: `/absolute/path/to/pyslang-mcp/.venv/bin/python`
- `args`: `["-m", "pyslang_mcp", "--transport", "stdio"]`

Future packaged install target:

```bash
pip install pyslang-mcp
```

Then point the MCP client at either:

- `command`: `pyslang-mcp`
- `args`: `[]`

or:

- `command`: `python`
- `args`: `["-m", "pyslang_mcp"]`

### Tool Input Rules

- Always provide `project_root`.
- Provide exactly one of `files` or `filelist`.
- Paths may be relative to `project_root` or absolute, but they must remain
  inside `project_root`.
- `include_dirs`, `defines`, and `top_modules` are optional.

Example `parse_files` payload:

```json
{
  "project_root": "/path/to/rtl-project",
  "files": [
    "rtl/pkg.sv",
    "rtl/top.sv"
  ],
  "include_dirs": [
    "include"
  ],
  "defines": {
    "WIDTH": "32"
  },
  "top_modules": [
    "top"
  ]
}
```

Example `parse_filelist` payload:

```json
{
  "project_root": "/path/to/rtl-project",
  "filelist": "compile/project.f"
}
```

Example `find_symbol` payload:

```json
{
  "project_root": "/path/to/rtl-project",
  "filelist": "compile/project.f",
  "query": "payload",
  "match_mode": "exact",
  "include_references": true
}
```

### Recommended Workflow

1. Start with `parse_filelist` or `parse_files` to confirm the project root,
   file expansion, include dirs, and defines are what you expect.
2. Run `get_diagnostics` to see parse or semantic issues early.
3. Use `list_design_units` and `describe_design_unit` to understand modules and
   packages.
4. Use `get_hierarchy` to inspect instantiation structure.
5. Use `find_symbol` for declaration and reference lookup.
6. Use `dump_syntax_tree_summary` and `preprocess_files` only when you need
   syntax or preprocessing context; they are intentionally compact.

### What Clients Should Expect Back

- Responses are JSON dictionaries.
- Large result lists include truncation metadata.
- `preprocess_files` is summary-oriented; it does not claim to reproduce a full
  standalone preprocessed output stream.
- If a path escapes the declared root, the call fails instead of reading it.

## Remote Deployment Direction

If the goal is to make `pyslang-mcp` feel more like well-known connectable MCPs
such as GitHub or Google Sheets, treat hosted access as a separate deployment
product surface, not as an extension of the current local `stdio` mode.

Current state:

- local-first `stdio` server is implemented
- hosted multi-user deployment is not implemented yet

Recommended hosted direction:

- add a secure HTTP MCP transport
- require authenticated workspaces
- isolate every user or repo workspace
- only analyze files that are present inside the provisioned workspace
- keep the same read-only tool semantics

See [`REMOTE_DEPLOYMENT.md`](./REMOTE_DEPLOYMENT.md) for the proposed hosted
architecture, security model, and rollout plan.

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
