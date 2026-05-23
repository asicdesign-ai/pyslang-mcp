# Comprehensive Skill vs LLM/MCP Comparison

Generated: 2026-05-23

This report summarizes two fresh local eval runs based on
`skills/pyslang-verilog-context/evals/SKILL_VS_LLM_EVAL_PLAN.md`.

- Plan-specific prompt/tool-sequencing eval:
  `skills/pyslang-verilog-context/evals/reports/comparison.json`
- Broader scalar MCP/skill benchmark:
  `reports/mcp_comparison_comprehensive_20260523/results.json`
- Interactive benchmark dashboard:
  `reports/mcp_comparison_comprehensive_20260523/index.html`
- 75-case real public RTL extension:
  `reports/real_examples_75/results.json`
- Combined 100-case summary:
  `reports/real_examples_75/combined_100_summary.md`

## What Was Executed

Validation and health checks:

```text
.venv/bin/python skills/pyslang-verilog-context/scripts/validate_eval_fixtures.py
ok: 12 cases, 7 fixture sources

.venv/bin/python -m pytest
37 passed in 3.40s
```

Eval runs:

```text
.venv/bin/python skills/pyslang-verilog-context/scripts/run_comparison_evals.py
wrote 12 comparison cases to skills/pyslang-verilog-context/evals/reports

.venv/bin/python scripts/run_mcp_comparison.py --output-dir reports/mcp_comparison_comprehensive_20260523
Cases: 25
Text/no skill exact answers: 13/25
MCP/no skill exact answers: 20/25
MCP/skill exact answers: 25/25

.venv/bin/python reports/real_examples_75/run_real75_comparison.py
Cases: 75
Text/no skill exact answers: 47/75
MCP/no skill exact answers: 75/75
Skill + MCP exact answers: 75/75

.venv/bin/python -m py_compile reports/real_examples_75/run_real75_comparison.py
```

## Methodology

The repo currently implements deterministic local comparison harnesses, not a
full blind autonomous LLM-judge harness for all four idealized arms in the plan.

Measured arms in the broader benchmark:

| Arm | Tooling | Skill context | Result type |
|---|---|---|---|
| Text/no skill | Source and filelist text only | No | deterministic scalar answer |
| MCP/no skill | Local `pyslang-mcp` stdio server | No | deterministic scalar answer |
| MCP/skill | Local `pyslang-mcp` stdio server | `rtl-lint-auditor` rule context | deterministic scalar answer |

The plan-specific eval also checked the `pyslang-verilog-context` workflow
expectations: parse mode selection, diagnostics first, design-unit discovery,
hierarchy, symbol lookup, syntax summary, and coding-change recheck discipline.

The 75-case extension used real public RTL files from six upstream repositories
and cycled through deterministic frontend-reading probes: diagnostic status,
design-unit count, and first design-unit port count. Its expected answers are
compiler-backed `pyslang-mcp` observations, so it is a compatibility and
frontend-reading benchmark rather than a substitute for human-labeled agent
reasoning tests.

## Overall Results

| Arm | Correct | Accuracy | Median local evidence time | Estimated total tokens |
|---|---:|---:|---:|---:|
| Text/no skill | 13/25 | 52% | 0.060 ms | 14,020 |
| MCP/no skill | 20/25 | 80% | 25.357 ms | 11,225 |
| MCP/skill | 25/25 | 100% | 25.358 ms | 92,017 |

Accuracy deltas:

| Comparison | Correct-answer delta |
|---|---:|
| MCP/no skill vs text/no skill | +7 |
| MCP/skill vs MCP/no skill | +5 |
| MCP/skill vs text/no skill | +12 |

The skill arm reached 100% in this benchmark, but with much higher estimated
token load because the harness includes the skill and rule text in the evidence
payload. Timings are local evidence-acquisition timings and exclude hidden LLM
inference.

## Real Public RTL Extension

| Arm | Correct | Accuracy | Median local evidence time | Estimated total tokens |
|---|---:|---:|---:|---:|
| Text/no skill | 47/75 | 63% | 0.001 ms | 184,353 |
| MCP/no skill | 75/75 | 100% | 0.552 ms | 47,493 |
| Skill + MCP | 75/75 | 100% | 4.197 ms | 122,718 |

Source mix:

| Repo | Commit | License | Cases |
|---|---|---|---:|
| `lowrisc-ibex` | `9742d89` | Apache-2.0 | 15 |
| `pulp-common-cells` | `63e1b67` | Solderpad-0.51 | 15 |
| `verilog-axis` | `48ff7a7` | MIT | 15 |
| `pulp-axi` | `e286bb1` | Solderpad-0.51 | 15 |
| `pulp-register-interface` | `d6e1d4c` | Solderpad-0.51 | 14 |
| `picorv32` | `87c89ac` | ISC | 1 |

By task:

| Task | Text/no skill | MCP/no skill | Skill + MCP |
|---|---:|---:|---:|
| Diagnostic status | 0/25 | 25/25 | 25/25 |
| Design-unit total | 24/25 | 25/25 | 25/25 |
| First-unit port count | 23/25 | 25/25 | 25/25 |

## Combined 100-Case Result

| Arm | Correct | Accuracy | Grade |
|---|---:|---:|---|
| Text/no skill | 60/100 | 60% | C- |
| MCP/no skill | 95/100 | 95% | A- |
| Skill + MCP | 100/100 | 100% | A |

Combined score:

```text
Text/no skill: 13/25 old + 47/75 new = 60/100
MCP/no skill: 20/25 old + 75/75 new = 95/100
Skill + MCP: 25/25 old + 75/75 new = 100/100
```

## Category Results

| Category | Cases | Text/no skill | MCP/no skill | MCP/skill |
|---|---:|---:|---:|---:|
| Diagnostics | 2 | 0/2 | 2/2 | 2/2 |
| Hierarchy | 3 | 3/3 | 3/3 | 3/3 |
| Interface | 4 | 4/4 | 4/4 | 4/4 |
| Preprocessing | 3 | 3/3 | 3/3 | 3/3 |
| Project loading | 2 | 1/2 | 2/2 | 2/2 |
| Skill lint / RTL coding bugs | 5 | 0/5 | 0/5 | 5/5 |
| Symbol inventory | 1 | 1/1 | 1/1 | 1/1 |
| Symbol references | 2 | 0/2 | 2/2 | 2/2 |
| Syntax | 1 | 1/1 | 1/1 | 1/1 |
| Type binding | 2 | 0/2 | 2/2 | 2/2 |

## RTL Reading Findings

The MCP-backed arms were most useful where plain source text lacks semantic
state:

- Diagnostics: text-only could not prove clean or incomplete frontend status;
  both MCP arms got 2/2.
- Symbol references: text-only missed compiler reference kind and hierarchical
  symbol path; both MCP arms got 2/2.
- Type binding: text-only missed package typedef binding; both MCP arms got 2/2.
- Project loading: MCP resolved normalized filelist/include closure; text-only
  missed one of two project-loading cases.

For simple direct-reading tasks, text was already enough:

- Direct hierarchy, ANSI interface counts, visible preprocessing tokens, and
  syntax keyword counts were all 100% for text/no skill and MCP arms.

## RTL Coding / Bug-Audit Findings

The coding-oriented slice used known buggy RTL fixtures and asked for exact
signals or cases under RTL lint/audit rules:

| Case | Expected | Text/no skill | MCP/no skill | MCP/skill |
|---|---|---|---|---|
| `edge_detect_polarity_bug_output` | `rise_pulse_o` | wrong/unknown | wrong/unknown | correct |
| `simple_counter_priority_bug_signal` | `enable_i` | wrong/unknown | wrong/unknown | correct |
| `register_pipe_stall_bug_signal` | `valid_q` | wrong/unknown | wrong/unknown | correct |
| `sync_fifo_count_bug_missing_case` | `simultaneous_push_pop` | wrong/unknown | wrong/unknown | correct |
| `apb_timer_irq_priority_bug_signal` | `clear_irq_i` | wrong/unknown | wrong/unknown | correct |

MCP/no skill proved the files parsed and exposed compiler context, but it did
not by itself apply the RTL audit rules needed to identify the coding bugs.
The skill context provided the missing rule discipline.

## Plan-Specific Skill Eval

The `pyslang-verilog-context` eval manifest ran 12 cases spanning design
summary, hierarchy, symbol lookup, diagnostics, clean-frontend functional bugs,
coding-change recheck workflow, timing-path structure, CDC boundary warning,
and public upstream RTL examples.

Expected tool evidence coverage was complete:

```text
47/47 expected pyslang-mcp tool calls succeeded
```

Notable included cases:

- `coding-change-with-recheck`: checked module interface and diagnostics before
  the proposed RTL edit path and required a diagnostics recheck.
- `clean-frontend-functional-bug`: verified that clean frontend diagnostics were
  not treated as a behavioral proof.
- `cdc-boundary-warning`: required structural evidence while explicitly avoiding
  CDC signoff claims.

## Acceptance-Criteria Readout

| Plan criterion | Result |
|---|---|
| Higher diagnostic accuracy than text tools | Passed: 2/2 in the 25-case run and 25/25 in the real RTL extension |
| Better symbol evidence than text search | Passed: 2/2 MCP vs 0/2 text for symbol references |
| Higher correct-tool sequencing | Passed in plan eval: 47/47 expected tool calls |
| Equal or better patch/coding success | Passed in bug-audit slice: skill arm 5/5 vs 0/5 baselines |
| Explicit limitations for frontend-clean and boundary tasks | Covered by manifest cases; deterministic harness does not grade prose quality |
| Lower overclaim rate than MCP-only | Not directly measured as an autonomous final-answer transcript metric |

## Verification Strategy

Verification was staged so eval interpretation depends on a healthy repo and
known fixture state:

1. Validate the skill eval manifest and fixtures.
2. Run the full Python test suite.
3. Run the plan-specific tool-sequencing harness and check expected tool-call
   coverage.
4. Run the broader 25-case scalar benchmark and preserve JSON/HTML outputs.
5. Clone public upstream RTL at recorded commits and run the 75-case extension.
6. Compile-check the new 75-case runner with `py_compile`.
7. Record limitations separately from the score so MCP evidence is not presented
   as simulation, synthesis, lint signoff, CDC/RDC signoff, timing signoff, or
   formal proof.

## Limitations

- Pure LLM was not executed as a live no-tool model arm; the implemented lower
  bound is deterministic text/no-skill evidence.
- The benchmark does not run independent autonomous agents or blind LLM judges.
  It checks exact scalar answers, tool evidence, and deterministic rule-guided
  outcomes.
- The coding-change eval validates workflow discipline and bug identification;
  it does not apply and diff an RTL patch in this run.
- Public upstream RTL examples may be present in model pretraining, so local and
  generated fixtures should remain the primary scored corpus.
- `pyslang-mcp` evidence is frontend/compiler context only. It is not simulation,
  synthesis, CDC/RDC, timing, formal, or full lint signoff.

## Conclusion

For RTL reading tasks that require compiler state, `pyslang-mcp` materially
improved the text-only baseline. For RTL coding/bug-audit tasks, MCP evidence
alone was insufficient; the skill/rule context was the differentiator. The
current data supports keeping the skill, but the next eval hardening step is a
true autonomous four-arm runner with saved transcripts, patch diffs, and blind
semantic grading.
