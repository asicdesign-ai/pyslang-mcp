# Verilog Analysis Function Delivery Report

Date: 2026-06-14

## Delivered

Implemented and documented five read-only Verilog/SystemVerilog analysis tools:

- `pyslang_find_member`
- `pyslang_get_assignments`
- `pyslang_trace_connectivity`
- `pyslang_get_instance_connections`
- `pyslang_summarize_diagnostics_by_code`

The analysis core, strict output schemas, FastMCP registrations, cache path,
hard bounds, structured errors, and stdio protocol contracts are covered by
focused tests. Connectivity results are documented as bounded structural
frontend evidence, not simulation, formal, CDC/RDC, synthesis, timing, or
complete netlist evidence.

## Public Guidance And Evals

Updated the public tool surface and workflow guidance in `AGENTS.md`,
`README.md`, `docs/architecture.md`, and
`skills/pyslang-verilog-context/SKILL.md`.

Added a public-safe SystemVerilog fixture and deterministic skill eval that
exercise diagnostic grouping, local member lookup, assignment lookup, focused
instance connections, and bounded connectivity tracing. The comparison report
records all 54 expected MCP calls across 13 cases as successful.

## Deterministic Comparison Results

The 25-case repository comparison completed with:

| Arm | Correct |
|---|---:|
| Text/no skill | 13/25 |
| MCP/no skill | 20/25 |
| MCP/skill | 25/25 |

The separate 75-case real public RTL comparison completed with:

| Arm | Correct |
|---|---:|
| Text/no skill | 47/75 |
| MCP/no skill | 75/75 |
| Skill + MCP | 75/75 |

These are deterministic frontend-reading benchmarks. They do not establish
simulation behavior, synthesis quality, CDC/RDC closure, timing closure,
formal correctness, or full lint signoff.

## Codex A/B Comparison

The isolated Codex harness uses the 20 existing repository RTL cases, two
arms, and three trials per case. It does not use the `verilog_debug` fixture.
Temporary homes disable unrelated apps and plugins, child stdin is closed, and
successful trial slots can be resumed after an interrupted run or external
usage-window reset.

All 120 trial slots completed successfully with exact-match scoring:

| Arm | Correct trials | Accuracy | Consistent cases | Required-tool use |
|---|---:|---:|---:|---:|
| No skill / no MCP | 39/60 | 65% | 16/20 | 0/60 |
| Skill + MCP | 57/60 | 95% | 20/20 | 60/60 |

The skill + MCP arm gained 18 correct trials and was consistent on every case.
The report intentionally does not normalize path prefixes, prose around scalar
answers, or define-value formatting; those remain exact-answer misses. Full
trial evidence is in `reports/codex_ab_20260614/`.

The first pass reached the external Codex usage window after 53 successful
trials. The resumed run reused those successful slots and completed the
remaining 67 after the documented reset time. The final report contains no
error, timeout, or invalid-output trials.

## Verification

The final verification sweep covers formatting, Ruff, pyright, coverage
pytest, security regressions, stdio protocol smoke, all 13 HDL examples, skill
fixture validation, deterministic comparison evals, the 25-case repository
comparison, the 75-case public RTL comparison, Python compilation of the
real-RTL harness, and the complete Codex A/B report.

Fresh results:

- Ruff formatting: 28 files already formatted
- Ruff lint: no findings
- pyright: 0 errors and 0 warnings
- pytest with coverage: 89 passed, 92% total coverage
- security regressions: 38 passed
- stdio protocol smoke: 1 passed
- HDL examples: 13 validated
- skill fixtures: 13 cases and 8 fixture sources validated
- skill comparison: 54/54 expected MCP calls successful
- Codex A/B report validation: 20 cases and 120 successful trials
