# AGENTS.md

This file is the public contributor and agent guidance for `pyslang-mcp`.
Read this first, then read [README.md](./README.md),
[CONTRIBUTING.md](./CONTRIBUTING.md), and
[REMOTE_DEPLOYMENT.md](./REMOTE_DEPLOYMENT.md) when the task touches
deployment.

## Mission

Build a professional, open-source MCP server that gives AI systems
compiler-backed, read-only understanding of Verilog and SystemVerilog projects
through `pyslang`.

The product is a semantic analysis MCP, not an EDA runtime. Keep scope tight
and technically honest.

## Product Scope

The public tool surface is:

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

Non-goals:

- simulation
- synthesis
- waveform viewing
- testbench generation
- RTL editing or refactoring through MCP tools
- remote code execution
- full IDE or language-server parity

## Architecture Constraints

- Use the official Python MCP SDK with `FastMCP`.
- Keep `stdio` transport as the primary path.
- Keep the server strictly read-only.
- Require explicit project roots or clearly client-provided roots.
- Do not read arbitrary paths outside declared project scope.
- Return compact, stable JSON outputs.
- Preserve output limits and truncation markers.
- Cache by project config plus file mtimes.
- Keep the analysis core separate from the MCP wrapper.

## Security Goals

- Treat project-root scoping, read-only behavior, and bounded outputs as
  regression-tested product guarantees.
- Keep auth and remote-deployment language narrow and technically honest.
- Mark deterministic abuse-case regressions with `pytest.mark.security` so CI
  can run the dedicated `security-regression` target.

## Remote Deployment Position

Remote/MaaS work must keep two tracks separate:

- public OSS MaaS for public HDL repositories only
- self-hosted internal MaaS for proprietary RTL inside an organization's own
  network, auth, logging, storage, and policy controls

Do not imply that the experimental `streamable-http` mode is a complete
production hosted security boundary. The single-server bearer-token path is a
bring-up aid, not broad enterprise auth or multi-tenant isolation.

## Implementation Notes

- Target stable MCP Python SDK v1.x behavior unless the project intentionally
  upgrades.
- `CompilationOptions.topModules` expects a `set[str]`.
- Assign `PreprocessorOptions.predefines` as a complete list rather than
  relying on in-place mutation before attaching options to a `Bag`.
- `pyslang_preprocess_files` returns preprocessing metadata plus source
  excerpts. Do not claim full standalone-preprocessor output fidelity unless a
  binding-level API has been validated and implemented.

## Quality Bar

Changes should preserve:

- installability with `uvx pyslang-mcp` or `pip install pyslang-mcp`
- safe read-only behavior
- useful multi-file Verilog/SystemVerilog analysis
- stable JSON outputs
- clear failures on bad input
- fixture-backed tests
- technically honest docs

## Public Repository Hygiene

- Do not commit private planning notes, personal handoff docs, local absolute
  paths, unpublished roadmap notes, or similar local-only markdown.
- Do not commit local virtual environments, generated secrets, bearer tokens,
  private repo URLs, private workspace names, or proprietary RTL.
- Public docs should describe released behavior, supported experimental paths,
  and clear limitations.
- Keep broad future work either in GitHub issues or in public-facing roadmap
  language that is suitable for an open-source repository.

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

## Working Style

- Prefer small, testable analysis functions before MCP wrappers.
- Preserve strict separation between core analysis and transport concerns.
- Be explicit about trust boundaries and unsupported cases.
- Keep documentation technically honest.
- If you validate new `pyslang` behavior, write it down in public repo docs.
