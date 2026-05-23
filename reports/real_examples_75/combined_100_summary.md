# 100-Case LLM/Text vs MCP vs Skill+MCP Comparison

Generated: 2026-05-23

This combines:

- The earlier 25-case benchmark in
  `reports/mcp_comparison_comprehensive_20260523/results.json`
- The new 75-case public RTL benchmark in
  `reports/real_examples_75/results.json`

## Added Real Examples

The new run used 75 real public RTL files from cloned upstream repositories.

| Repo | Commit | License | Cases |
|---|---|---|---:|
| `lowrisc-ibex` | `9742d89` | Apache-2.0 | 15 |
| `pulp-common-cells` | `63e1b67` | Solderpad-0.51 | 15 |
| `verilog-axis` | `48ff7a7` | MIT | 15 |
| `pulp-axi` | `e286bb1` | Solderpad-0.51 | 15 |
| `pulp-register-interface` | `d6e1d4c` | Solderpad-0.51 | 14 |
| `picorv32` | `87c89ac` | ISC | 1 |

The 75 added cases cycle through:

- frontend diagnostic status
- design-unit inventory
- first design-unit port count

## New 75-Case Result

| Arm | Correct | Accuracy |
|---|---:|---:|
| Text/no skill | 47/75 | 63% |
| MCP/no skill | 75/75 | 100% |
| Skill + MCP | 75/75 | 100% |

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

The combined score is:

```text
Text/no skill: 13/25 old + 47/75 new = 60/100
MCP/no skill: 20/25 old + 75/75 new = 95/100
Skill + MCP: 25/25 old + 75/75 new = 100/100
```

## Interpretation

The 75 real-source reading cases confirm the main pattern from the original
eval: text-only heuristics do fine on simple visible structure, but fail on
questions that require compiler/frontend state.

The biggest gap was diagnostic status:

```text
Text/no skill: 0/25
MCP/no skill: 25/25
Skill + MCP: 25/25
```

For these new reading-only cases, MCP/no skill and Skill + MCP tied. That is
expected: the task answers are direct compiler observations, and the skill adds
workflow discipline rather than new facts.

The skill's measurable advantage still comes from the original RTL
coding/bug-audit slice:

```text
Text/no skill: 0/5
MCP/no skill: 0/5
Skill + MCP: 5/5
```

MCP can prove parse/semantic context, but it does not automatically apply RTL
audit rules such as stall preservation, IRQ priority, edge polarity, or FIFO
push/pop concurrency. The skill/rule context supplies that missing discipline.

## Verification Strategy

The combined result is based on two verified local runs:

1. Fixture and repo health:

   ```text
   .venv/bin/python skills/pyslang-verilog-context/scripts/validate_eval_fixtures.py
   ok: 12 cases, 7 fixture sources

   .venv/bin/python -m pytest
   37 passed in 3.40s
   ```

2. Plan-specific skill/tool-sequencing eval:

   ```text
   .venv/bin/python skills/pyslang-verilog-context/scripts/run_comparison_evals.py
   47/47 expected pyslang-mcp tool calls succeeded
   ```

3. Existing 25-case scalar benchmark:

   ```text
   .venv/bin/python scripts/run_mcp_comparison.py \
     --output-dir reports/mcp_comparison_comprehensive_20260523
   ```

4. New 75-case real public RTL extension:

   ```text
   .venv/bin/python reports/real_examples_75/run_real75_comparison.py
   ```

5. Runner syntax check:

   ```text
   .venv/bin/python -m py_compile reports/real_examples_75/run_real75_comparison.py
   ```

The 75-case extension records source repo commits and licenses, skips files that
cannot produce deterministic compiler-backed expected answers, and scores exact
scalar answers only. The older 25-case run supplies the RTL coding/bug-audit
signal; the new 75-case run supplies broader real-source frontend-reading
coverage.

## Limits

- The 75 new examples are real public RTL files, but the benchmark questions are
  deterministic scalar probes.
- Expected answers for the new 75-case run are compiler-backed `pyslang-mcp`
  observations, not independent human labels.
- This is still not a blind autonomous LLM judge with full transcripts.
- The new 75-case slice is RTL reading/structure only; the coding/bug-audit
  signal comes from the earlier 25-case benchmark.
- `pyslang-mcp` remains frontend/compiler evidence only. It is not simulation,
  synthesis, CDC/RDC, timing, formal, or full lint signoff.

## Artifacts

- `reports/real_examples_75/run_real75_comparison.py`
- `reports/real_examples_75/results.json`
- `reports/real_examples_75/summary.md`
- `reports/mcp_comparison_comprehensive_20260523/results.json`
