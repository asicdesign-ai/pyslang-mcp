# Real Public RTL 75-Case Comparison

Generated: 2026-05-23T11:14:06+00:00

## Sources

| Repo | Commit | License | Cases |
|---|---|---|---:|
| `lowrisc-ibex` | `9742d89` | Apache-2.0 | 15 |
| `pulp-common-cells` | `63e1b67` | Solderpad-0.51 | 15 |
| `verilog-axis` | `48ff7a7` | MIT | 15 |
| `pulp-axi` | `e286bb1` | Solderpad-0.51 | 15 |
| `pulp-register-interface` | `d6e1d4c` | Solderpad-0.51 | 14 |
| `picorv32` | `87c89ac` | ISC | 1 |

## Overall

| Arm | Correct | Accuracy | Median local evidence time | Est. tokens |
|---|---:|---:|---:|---:|
| Text/no skill | 47/75 | 63% | 0.001 ms | 184,353 |
| MCP/no skill | 75/75 | 100% | 0.552 ms | 47,493 |
| Skill + MCP | 75/75 | 100% | 4.197 ms | 122,718 |

## By Task

| Task | Cases | Text/no skill | MCP/no skill | Skill + MCP |
|---|---:|---:|---:|---:|
| `design_unit_total` | 25 | 24/25 | 25/25 | 25/25 |
| `diagnostic_status` | 25 | 0/25 | 25/25 | 25/25 |
| `first_unit_port_count` | 25 | 23/25 | 25/25 | 25/25 |

## By Repo

| Repo | Cases | Text/no skill | MCP/no skill | Skill + MCP |
|---|---:|---:|---:|---:|
| `lowrisc-ibex` | 15 | 9/15 | 15/15 | 15/15 |
| `picorv32` | 1 | 1/1 | 1/1 | 1/1 |
| `pulp-axi` | 15 | 9/15 | 15/15 | 15/15 |
| `pulp-common-cells` | 15 | 9/15 | 15/15 | 15/15 |
| `pulp-register-interface` | 14 | 9/14 | 14/14 | 14/14 |
| `verilog-axis` | 15 | 10/15 | 15/15 | 15/15 |

## Notes

- These are real public RTL source files, but the questions are deterministic scalar probes.
- Expected answers are compiler-backed `pyslang-mcp` observations, so this is an MCP-grounded reading benchmark rather than an independent human-labeled benchmark.
- Skill + MCP follows the `pyslang-verilog-context` discipline by parsing and checking diagnostics before structural queries.
- On these reading tasks, Skill + MCP and MCP/no skill have the same exact-answer accuracy; the skill mainly adds sequencing and limitation discipline rather than new RTL bug rules.

## Verification Strategy

The 75-case run was verified with this process:

1. Clone public upstream RTL repositories under `reports/real_examples_75/repos/`.
2. Record each repository commit and license in the report.
3. Select real `.sv` and `.v` files from implementation-oriented directories
   with file-size limits to keep the local compiler-backed run bounded.
4. Skip files where a deterministic expected answer cannot be derived from
   `pyslang-mcp`.
5. Run three arms per accepted case:
   - Text/no skill: local source-text heuristics only.
   - MCP/no skill: targeted `pyslang-mcp` tool calls.
   - Skill + MCP: parse and diagnostics first, then the structural query.
6. Score exact scalar answers against compiler-backed observations.
7. Run `py_compile` on `run_real75_comparison.py` after generation.

This is a real-source frontend-reading benchmark. It is not a blind autonomous
LLM-judge benchmark and does not claim simulation, synthesis, CDC/RDC, timing,
formal, or full lint signoff.
