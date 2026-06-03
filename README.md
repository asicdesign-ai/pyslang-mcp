# pyslang-mcp
<!-- mcp-name: io.github.ariklapid/pyslang-mcp -->

[![CI](https://github.com/ariklapid/pyslang-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/ariklapid/pyslang-mcp/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/pyslang-mcp.svg)](https://pypi.org/project/pyslang-mcp/)
![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)
![Status](https://img.shields.io/badge/status-early--stage-orange)
![Transport](https://img.shields.io/badge/transport-stdio-informational)

`pyslang-mcp` is a local Model Context Protocol server that gives AI agents
compiler-backed, read-only context for Verilog and SystemVerilog projects.

It wraps [`pyslang`](https://pypi.org/project/pyslang/) so an MCP client can ask
questions against parsed and elaborated HDL instead of plain text:

- What modules, interfaces, and packages are in this filelist?
- What diagnostics does the compiler frontend report?
- What is the instance hierarchy below this top?
- Where is this symbol declared or referenced?
- Did my include paths, defines, and nested `.f` files resolve as expected?

This is not a simulator, synthesizer, waveform viewer, linter replacement, or
RTL refactoring tool. It is a small semantic analysis service for local HDL
checkouts.

That read-only boundary is intentional. It keeps the server side-effect free,
reduces the blast radius in IP-protected workspaces, and makes it safer to use
in local and CI environments.

My workflow choice is deliberate too: I let the LLM do the actual RTL coding,
then use `pyslang-mcp` as the compile/elab-backed reader, checker, and
explainer for the code that already exists. In other words, the model drafts
the RTL and the MCP server verifies what the compiler frontend sees.

> [!NOTE]
> The project is currently early-stage and published on
> [PyPI](https://pypi.org/project/pyslang-mcp/) and the
> [MCP Registry](https://registry.modelcontextprotocol.io/?q=pyslang-mcp) for
> local stdio use.

## Why ASIC And EDA Engineers Might Care

Most AI coding tools are good at searching text. HDL usually needs more than
that.

In real projects, useful answers often depend on filelists, packages, includes,
defines, generate blocks, and hierarchy. `pyslang-mcp` gives an agent a compact
compiler-backed view of that structure, while keeping the server read-only and
scoped to a project root you provide.

Good fits:

- triaging parse and semantic diagnostics before asking an agent to reason
  about RTL
- checking what a `.f` file expands to
- listing design units in a block or small IP
- finding a declaration without chasing comments and stale grep hits
- getting hierarchy and port-connection context for review/debug prompts
- giving workflow agents HDL context without handing them an EDA runtime

## Quickstart

Install the package:

```bash
pip install pyslang-mcp
```

Run the local stdio server:

```bash
pyslang-mcp
```

For contributor setup, clone the repo and install it in editable mode:

```bash
git clone https://github.com/ariklapid/pyslang-mcp.git
cd pyslang-mcp
python -m venv .venv
./.venv/bin/pip install -e '.[dev]'
```

Run the checkout stdio server:

```bash
./.venv/bin/python -m pyslang_mcp
```

The installed console script works too:

```bash
./.venv/bin/pyslang-mcp
```

Run tests:

```bash
./.venv/bin/pytest
```

## MCP Client Config

Use local `stdio`. The MCP client should launch the server on the same machine,
VM, or dev container that can see your RTL checkout.

```json
{
  "mcpServers": {
    "pyslang-mcp": {
      "command": "pyslang-mcp",
      "args": []
    }
  }
}
```

For editable checkout installs, point the command at the checkout virtual
environment instead:

```json
{
  "mcpServers": {
    "pyslang-mcp": {
      "command": "/absolute/path/to/pyslang-mcp/.venv/bin/python",
      "args": ["-m", "pyslang_mcp"]
    }
  }
}
```

Tool calls must provide a `project_root`. Source paths, filelists, and include
directories may be absolute or relative, but they must stay under that root.

## Minimal Tool Payloads

Analyze explicit files:

```json
{
  "project_root": "/path/to/rtl-project",
  "files": ["rtl/pkg.sv", "rtl/top.sv"],
  "include_dirs": ["include"],
  "defines": {
    "WIDTH": "32"
  },
  "top_modules": ["top"]
}
```

Analyze a filelist:

```json
{
  "project_root": "/path/to/rtl-project",
  "filelist": "compile/project.f"
}
```

Find a symbol:

```json
{
  "project_root": "/path/to/rtl-project",
  "filelist": "compile/project.f",
  "query": "payload",
  "match_mode": "exact",
  "include_references": true
}
```

## Tools

| Need | Tool |
|---|---|
| Load explicit files | `pyslang_parse_files` |
| Load a `.f` filelist | `pyslang_parse_filelist` |
| Get parse and semantic diagnostics | `pyslang_get_diagnostics` |
| List modules, interfaces, and packages | `pyslang_list_design_units` |
| Inspect one design unit | `pyslang_describe_design_unit` |
| Walk the elaborated instance tree | `pyslang_get_hierarchy` |
| Find declarations and references | `pyslang_find_symbol` |
| Summarize syntax node shapes | `pyslang_dump_syntax_tree_summary` |
| Check preprocessing metadata and excerpts | `pyslang_preprocess_files` |
| Get a compact project overview | `pyslang_get_project_summary` |

Typical flow:

1. Start with `pyslang_parse_filelist` or `pyslang_parse_files`.
2. Run `pyslang_get_diagnostics`.
3. Use `pyslang_list_design_units` to see what the compiler frontend found.
4. Use `pyslang_describe_design_unit`, `pyslang_get_hierarchy`, or
   `pyslang_find_symbol` for the actual review/debug question.

## Filelist Support

The current parser intentionally supports a practical subset used by many RTL
flows:

- source file entries
- nested filelists with `-f` and `-F`
- include directories with `+incdir+...`, `-I dir`, and `-Idir`
- defines with `+define+...`, `-D NAME`, and `-DNAME`

Unsupported filelist tokens are reported in the tool output instead of being
silently ignored.

## Example Agent Prompts

Use this server when compiler-backed context matters:

- "Parse `compile/project.f` with `+define+DEBUG` and group diagnostics by
  source file."
- "List every design unit in this project and identify the likely top modules."
- "From `top`, show the instance hierarchy down to depth 4."
- "Describe module `axi_dma_top`: ports, child instances, and declared names."
- "Find the declaration and references for `payload_valid`."
- "Confirm whether `legacy_widget` is instantiated anywhere the elaborator
  sees it."
- "Show the resolved files, include dirs, defines, and unsupported entries from
  this filelist."

For single-line questions, comments, naming searches, or partial/incomplete
source sets, regular `rg`, editor search, or direct file reading is usually
faster and clearer.

## Guardrails

- Read-only MCP tools. No RTL edits, formatting, simulation, or synthesis.
- Strict project-root scoping. Paths outside `project_root` are rejected.
- Compact JSON responses with truncation metadata for large result sets.
- Process-local cache keyed by project config and tracked file mtimes.
- `pyslang_preprocess_files` is summary-oriented. It returns preprocessing
  metadata and source excerpts, not a guaranteed full standalone preprocessed
  stream.
- `streamable-http` remains experimental. The internal MaaS path wraps it with
  a bearer token for single-server use, but it is not a complete production
  hosted security boundary by itself.

## Remote MaaS Direction

Remote MaaS is planned as two separate tracks, not as one generic hosted mode:

- **Plan A: public OSS MaaS.** A convenience/demo service for public
  open-source HDL repositories. This is not suitable for proprietary or
  confidential RTL.
- **Plan B: internal MaaS.** A self-hosted deployment pattern for companies to
  run inside their own network, close to internal repositories, auth, logging,
  and security controls.

Start with the [internal MaaS quickstart](./docs/internal-maas-quickstart.md)
for a single internal server. See [REMOTE_DEPLOYMENT.md](./REMOTE_DEPLOYMENT.md)
for the full Plan A / Plan B split.

Docker Compose is the recommended bring-up path because it avoids Python setup
issues and mounts the RTL checkout read-only. Docker is not required; the
quickstart also includes a native Python path for corporate servers where
containers are not available.

## HDL Example Corpus

The repo includes generated HDL examples under
[`examples/hdl`](./examples/hdl/):

- clean reference projects from single modules to small IP-style examples
- intentionally buggy variants labeled `easy`, `medium`, and `hard`
- local validation hooks for both `pyslang` and `verilator --lint-only`

Run the full corpus validator:

```bash
./.venv/bin/python scripts/validate_hdl_examples.py
```

Run the CI smoke subset:

```bash
./.venv/bin/python scripts/validate_hdl_examples.py --smoke-only
```

## Using With Broader RTL Skills

If your agent environment already has a broad RTL skill such as
`rtl-analysis`, `rtl-audit`, or `llm-based-verilog-analysis`, use
`pyslang-verilog-context` as the fine-grained compiler-evidence layer beneath
that broader skill.

Recommended setup:

1. Configure the `pyslang-mcp` server in your MCP client so the agent can call
   the read-only `pyslang_*` tools.
2. Install or copy the `pyslang-verilog-context` skill from
   [`skills/pyslang-verilog-context`](./skills/pyslang-verilog-context/).
3. Add a delegation note like this to your broader RTL skill:

```text
For Verilog/SystemVerilog tasks, use $pyslang-verilog-context before making
claims about diagnostics, design units, ports, hierarchy, declarations,
references, includes, defines, or filelist behavior. Treat its output as
compiler frontend evidence only. Do not present it as simulation, synthesis,
timing, CDC/RDC, formal, or full lint signoff.
```

The intended flow is:

```text
user RTL request
  -> broad RTL analysis/audit skill
  -> pyslang-verilog-context
  -> pyslang-mcp compiler-backed evidence
  -> final answer with evidence and limitations
```

This keeps high-level RTL review policy in the broad skill while grounding
Verilog/SystemVerilog structure, diagnostics, hierarchy, symbols, includes, and
filelists in `pyslang`.

## Evaluation Benchmarks

The repo includes a `pyslang-verilog-context` skill eval suite under
[`skills/pyslang-verilog-context/evals`](./skills/pyslang-verilog-context/evals/)
and comparison reports under [`reports/`](./reports/). The current benchmark
compares three local evidence modes:

- text/no skill: source and filelist text heuristics only
- MCP/no skill: targeted `pyslang-mcp` tool calls
- skill + MCP: `pyslang-verilog-context` sequencing with `pyslang-mcp`

Latest local result from 2026-05-23:

| Benchmark | Text/no skill | MCP/no skill | Skill + MCP |
|---|---:|---:|---:|
| 100 HDL analysis cases | 60/100 | 95/100 | 100/100 |

The benchmark mixes deterministic repo-local HDL fixtures with real public RTL
source files. The local fixtures exercise targeted behaviors such as filelists,
hierarchy, symbols, diagnostics, clean-frontend functional bugs, and RTL coding
and bug-audit discipline. The real public RTL cases use source files from
`lowrisc-ibex`,
`pulp-common-cells`, `verilog-axis`, `pulp-axi`,
`pulp-register-interface`, and `picorv32`. They exercise frontend diagnostic
status, design-unit inventory, and first-unit port counts on real source files.
See [docs/evaluation-benchmarks.md](./docs/evaluation-benchmarks.md) for the
prompt/task shapes and MCP functions used.

Verification commands used for the reported run:

```bash
./.venv/bin/python skills/pyslang-verilog-context/scripts/validate_eval_fixtures.py
./.venv/bin/python -m pytest
./.venv/bin/python skills/pyslang-verilog-context/scripts/run_comparison_evals.py
./.venv/bin/python scripts/run_mcp_comparison.py --output-dir reports/mcp_comparison_comprehensive_20260523
./.venv/bin/python reports/real_examples_75/run_real75_comparison.py
./.venv/bin/python -m py_compile reports/real_examples_75/run_real75_comparison.py
```

These are deterministic scalar harnesses, not blind autonomous LLM-judge runs.
`pyslang-mcp` evidence remains frontend/compiler context only, not simulation,
synthesis, CDC/RDC, timing, formal, or full lint signoff.

Documentation-only eval/report updates do not require a PyPI release. A PyPI
release is warranted when package code, public tool behavior, schemas, runtime
dependencies, CLI behavior, or user-facing install/runtime docs change in a way
published users need.

## Project Status

Implemented:

- `FastMCP` stdio server
- CLI entrypoint via `python -m pyslang_mcp` and `pyslang-mcp`
- project loader with root checks and `.f` parsing
- pyslang-backed diagnostics, design-unit listing, hierarchy, symbol lookup,
  syntax summaries, and project summaries
- bounded in-memory cache
- fixture-backed tests and Ubuntu CI for Python 3.11 and 3.12
- package smoke CI from a built wheel
- manual PyPI Trusted Publishing release workflow with release-gate tests
- PyPI package: [`pyslang-mcp`](https://pypi.org/project/pyslang-mcp/)
- MCP Registry entry:
  [`io.github.ariklapid/pyslang-mcp`](https://registry.modelcontextprotocol.io/?q=pyslang-mcp)
- internal MaaS bring-up artifacts: Dockerfile, Docker Compose config, native
  Python fallback instructions, systemd template, bearer-token HTTP option, and
  a single-server quickstart

Not done yet:

- schema freeze for a more mature API-stable release
- broad platform validation beyond the current Linux-focused CI path
- production MaaS hardening for broad team use: SSO, multi-workspace routing,
  Kubernetes deployment, source-safe metrics, and reverse-proxy examples

## Development

Useful commands:

```bash
./.venv/bin/ruff check .
./.venv/bin/pyright
./.venv/bin/pytest
```

Architecture and contribution docs:

- [docs/architecture.md](./docs/architecture.md)
- [docs/internal-maas-quickstart.md](./docs/internal-maas-quickstart.md)
- [REMOTE_DEPLOYMENT.md](./REMOTE_DEPLOYMENT.md)
- [docs/mcp-registry.md](./docs/mcp-registry.md)
- [CONTRIBUTING.md](./CONTRIBUTING.md)

## License

Apache-2.0. See [LICENSE](./LICENSE).
