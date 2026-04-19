# `pyslang-mcp` Plan

**Goal**
- Build a standalone, open-source MCP server that gives AI clients compiler-backed, read-only understanding of Verilog/SystemVerilog projects through `pyslang`.
- Position it as a semantic analysis MCP, not a simulator, synthesizer, waveform tool, or code generator.

**Repo Decision**
- Use a separate GitHub repo, not a folder under `asic-ai-workflows`.
- Reason: this is a general-purpose tool with its own packaging, release cadence, CI, docs, and MCP registry identity.
- Keep `asic-ai-workflows` as a consumer later with example configs or integration docs.

**Product Thesis**
- There appears to be a gap for a public OSS MCP specifically wrapping `pyslang`.
- Existing adjacent options are commercial compiler-backed MCPs or tool-centric MCPs around Verible, Yosys, Verilator, or larger EDA flows.
- The differentiation should be: Python-native, compiler-backed, token-efficient semantic inspection of local HDL projects.

**V1 Scope**
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

**Explicit Non-Goals For V1**
- Simulation
- Synthesis
- Waveform viewing
- Testbench generation
- RTL editing or refactoring
- Remote code execution
- Full IDE language-server parity

**Research Phase**
1. Reconfirm the gap before naming and publishing by checking GitHub, the MCP Registry, and community lists for any `pyslang` or `slang` MCP that may have appeared.
2. Spike `pyslang` directly with small scripts to validate the exact APIs for syntax trees, compilation, diagnostics, symbol traversal, and hierarchy extraction.
3. Verify how `pyslang` handles multi-file projects, packages, imports, include dirs, macro defines, and `.f` filelists.
4. Measure practical behavior on representative fixtures: single-file RTL, package-heavy SV, macro/include usage, and intentionally broken code.
5. Check packaging realities: supported Python versions, wheel availability, platform support, install time, and dependency footprint.
6. Verify license compatibility for `pyslang`, the MCP SDK, and all transitive runtime dependencies.

**Architecture Plan**
- Use the official Python MCP SDK with `FastMCP`.
- Start with `stdio` transport only.
- Make the server strictly read-only.
- Require explicit project roots or use client-provided roots.
- Cache analysis results by project config plus file mtimes.
- Return stable, compact JSON outputs; never dump raw full ASTs by default.
- Add size limits, truncation markers, and clear error types for bad paths, parse errors, and unsupported queries.

**Proposed Repo Layout**
- `README.md`
- `pyproject.toml`
- `src/pyslang_mcp/__init__.py`
- `src/pyslang_mcp/__main__.py`
- `src/pyslang_mcp/server.py`
- `src/pyslang_mcp/project_loader.py`
- `src/pyslang_mcp/analysis.py`
- `src/pyslang_mcp/serializers.py`
- `src/pyslang_mcp/cache.py`
- `src/pyslang_mcp/types.py`
- `tests/`
- `tests/fixtures/`
- `examples/`
- `.github/workflows/ci.yml`
- `.github/workflows/publish.yml`
- `ARCHITECTURE.md`
- `ROADMAP.md`
- `CHANGELOG.md`
- `LICENSE`

**Implementation Plan**
1. Scaffold the repo and packaging so `uv run pyslang-mcp` works locally.
2. Implement project loading first: file paths, include dirs, defines, and `.f` filelist parsing.
3. Implement the minimal analysis core around `pyslang` with direct Python scripts before exposing MCP tools.
4. Freeze output schemas for diagnostics, design units, hierarchy nodes, and symbol hits.
5. Add MCP tools only after the core analysis functions are stable and tested.
6. Add caching and output limits after the first end-to-end tool calls work.
7. Write client examples for Claude Code, Claude Desktop, Cursor, and generic `uvx` usage.

**Testing Plan**
- Unit tests for filelist parsing, path normalization, config hashing, cache invalidation, and output serialization.
- Fixture-based integration tests for:
  - single-file Verilog parse
  - multi-file SystemVerilog package/import flow
  - include directory resolution
  - macro define handling
  - syntax error reporting
  - unresolved reference behavior
  - hierarchy extraction
  - symbol lookup
- MCP-level tests that start the server and call tools through the SDK or MCP Inspector.
- Golden-output tests for JSON response stability.
- Performance smoke tests on medium-size fixtures to catch regressions in latency and memory.
- CI on `ubuntu-latest` first; add macOS and Windows only after confirming `pyslang` support is reliable there.

**Tooling Plan**
- `uv` for packaging and local dev
- `pytest` for tests
- `ruff` for lint and formatting
- `pyright` or `mypy` for type checking
- GitHub Actions for CI
- PyPI trusted publishing for releases
- MCP Inspector for manual protocol checks

**Documentation Plan**
- README: problem statement, scope, quickstart, tool list, client setup, examples, non-goals.
- ARCHITECTURE: analysis pipeline, caching, limits, trust boundaries.
- ROADMAP: v1, v1.1, v2.
- CONTRIBUTING: dev setup, test commands, fixture conventions.
- SECURITY: clarify read-only behavior, filesystem scope, and output truncation rules.

**Publishing Plan**
1. Choose final names early and check availability for GitHub repo, PyPI package, and MCP registry namespace.
2. Recommended names:
   - Repo: `pyslang-mcp`
   - PyPI: `pyslang-mcp`
   - Python package: `pyslang_mcp`
   - Command: `pyslang-mcp`
3. Publish tagged releases to PyPI so clients can run `uvx pyslang-mcp`.
4. Add GitHub release notes with supported platforms and known limitations.
5. Publish to the MCP Registry under the GitHub namespace, likely `io.github.<owner>/pyslang-mcp`.
6. Automate registry publication and package release with GitHub Actions OIDC once the first manual publish succeeds.

**Milestones**
- M0: research spike and exact API validation
- M1: repo scaffold and local runnable server
- M2: parsing, filelists, preprocessing, diagnostics
- M3: design-unit listing, hierarchy, symbol lookup
- M4: hardening, caching, schema freeze, docs
- M5: PyPI release, registry publish, announcement

**V1 Acceptance Criteria**
- Installs cleanly with `uvx` or `pip`
- Can analyze a real multi-file SV project with include dirs and defines
- Returns stable JSON for diagnostics, units, hierarchy, and symbol lookups
- Fails clearly on malformed inputs and broken projects
- Has fixture-backed CI
- Has copy-paste client setup docs
- Is published on GitHub and packaged for easy client consumption

**Primary Risks**
- `pyslang` may expose some semantic queries less directly than expected.
- Hierarchy and symbol lookup may require deeper compiler traversal than the initial spike suggests.
- Output size can explode if AST data is not summarized aggressively.
- Real-world filelists and preprocessing conventions vary widely; support should be documented narrowly and honestly.

**Immediate First Issues To Open**
- repo scaffold
- investigate exact `pyslang` APIs for symbols and hierarchy
- implement `.f` parser
- build fixture corpus
- freeze response schemas
- implement diagnostics tools
- implement design-unit tools
- implement hierarchy tools
- implement symbol lookup
- add MCP integration tests
- add client configs
- publish first alpha release

**Reference Links**
- `pyslang`: https://pypi.org/project/pyslang/
- `slang`: https://github.com/MikePopoloski/slang
- Python MCP SDK: https://github.com/modelcontextprotocol/python-sdk
- MCP servers docs: https://github.com/modelcontextprotocol/servers
- MCP Registry: https://github.com/modelcontextprotocol/registry
- `Pyverilog`: https://pypi.org/project/pyverilog/
- `hdlConvertor`: https://github.com/Nic30/hdlConvertor
- AMIQ DVT MCP Server: https://eda.amiq.com/products/dvt-mcp-server
- `MCP4EDA`: https://github.com/NellyW8/MCP4EDA
