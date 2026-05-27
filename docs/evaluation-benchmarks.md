# Evaluation Benchmark Details

This page documents the prompt/task shapes and MCP tool coverage behind the
README benchmark summary.

The recorded 2026-05-23 result combines:

- a 25-case local scalar benchmark in
  `reports/mcp_comparison_comprehensive_20260523/results.json`
- a 75-case real public RTL scalar benchmark in
  `reports/real_examples_75/results.json`
- a separate `pyslang-verilog-context` tool-sequencing smoke report in
  `skills/pyslang-verilog-context/evals/reports/comparison.json`

No live LLM judge is used. These are deterministic local harnesses.

## Evidence Modes

The scalar benchmark compares three evidence modes:

| Mode | Meaning |
|---|---|
| Text/no skill | Source and filelist text heuristics only. No MCP calls and no skill rule context. |
| MCP/no skill | Targeted `pyslang-mcp` tool calls. No skill rule context. |
| Skill + MCP | Skill-guided use of `pyslang-mcp`, with evidence sequencing and limitation discipline. |

For the 25 local scalar cases, each MCP prompt includes:

- mode
- project name
- category
- task question
- whether skill/rule context should be used
- required MCP tool names
- instruction to return one scalar answer, or `unknown`

For the 75 real public RTL cases, the harness cycles through three task
templates:

| Task template | Cases | Skill + MCP tool sequence |
|---|---:|---|
| Frontend diagnostic status | 25 | `pyslang_parse_files`, `pyslang_get_diagnostics` |
| Design-unit count | 25 | `pyslang_parse_files`, `pyslang_get_diagnostics`, `pyslang_list_design_units` |
| First design-unit port count | 25 | `pyslang_parse_files`, `pyslang_get_diagnostics`, `pyslang_list_design_units`, `pyslang_describe_design_unit` |

The real public RTL source files come from `lowrisc-ibex`,
`pulp-common-cells`, `verilog-axis`, `pulp-axi`,
`pulp-register-interface`, and `picorv32`.

## 25 Local Scalar Tasks

These are exact scalar-answer tasks over generated repo-local examples,
intentionally buggy generated variants, and compact parser/test fixtures.

| Case | Prompt task | Required MCP function |
|---|---|---|
| `sync_child_path` | What is the `hierarchical_path` of the only child instance under top instance `sync_fifo`? | `pyslang_get_hierarchy` |
| `sync_child_definition` | What module definition is instantiated by child instance `u_sync_fifo_mem`? | `pyslang_get_hierarchy` |
| `sync_output_ports` | How many output ports does the `sync_fifo` design unit expose? | `pyslang_describe_design_unit` |
| `sync_tracked_paths` | How many normalized `tracked_paths` are in the loaded project? | `pyslang_get_project_summary` |
| `sync_package_include` | Which file includes `fifo_defs.svh` and has `PackageDeclaration` as its only top-level member? | `pyslang_dump_syntax_tree_summary` |
| `push_fire_reference_kind` | For symbol `push_fire`, what `reference_kind` is reported for its named-value reference? | `pyslang_find_symbol` |
| `timer_core_ports` | How many total ports does `timer_core` expose? | `pyslang_describe_design_unit` |
| `tick_hier_path` | What `hierarchical_path` is reported for the `tick` variable declaration? | `pyslang_find_symbol` |
| `prescale_q_count` | How many `prescale_q` declarations are reported? | `pyslang_find_symbol` |
| `buggy_apb_diagnostics` | How many parse and semantic diagnostics are reported for the buggy APB timer project? | `pyslang_get_diagnostics` |
| `broken_project_status` | What `project_status.status` is reported for the broken fixture? | `pyslang_get_diagnostics` |
| `data_t_reference_kind` | For symbol `data_t`, what `reference_kind` is reported for a declared-type use? | `pyslang_find_symbol` |
| `multi_file_width_define` | What effective `WIDTH` preprocessor define is reported? | `pyslang_preprocess_files` |
| `multi_file_child_path` | What is the `hierarchical_path` of the child instance under top instance `top`? | `pyslang_get_hierarchy` |
| `apb_design_unit_total` | How many project-local design units are in the APB timer project? | `pyslang_list_design_units` |
| `sync_pkg_function_count` | How many `FunctionDeclaration` members are in `sync_fifo_pkg`? | `pyslang_describe_design_unit` |
| `sync_mem_port_count` | How many total ports does `sync_fifo_mem` expose? | `pyslang_describe_design_unit` |
| `timer_ctrl_type_reference_count` | How many references are reported for `timer_ctrl_t`? | `pyslang_find_symbol` |
| `tap_delay_for_keyword_count` | How many `ForKeyword` syntax nodes are reported in `tap_delay_line.sv`? | `pyslang_dump_syntax_tree_summary` |
| `apb_timer_include_path` | Which include path is reported by the APB timer package file? | `pyslang_preprocess_files` |
| `edge_detect_polarity_bug_output` | Under RTL audit rules, which output carries the edge polarity bug? | `pyslang_get_diagnostics` |
| `simple_counter_priority_bug_signal` | Under RTL audit rules, which control signal incorrectly has priority? | `pyslang_get_diagnostics` |
| `register_pipe_stall_bug_signal` | Under RTL audit rules, which state signal is incorrectly cleared on stall? | `pyslang_get_diagnostics` |
| `sync_fifo_count_bug_missing_case` | Under RTL audit rules, which missing concurrency case breaks the FIFO count update? | `pyslang_get_diagnostics` |
| `apb_timer_irq_priority_bug_signal` | Under RTL audit rules, which signal's clear action can be overwritten by a later IRQ set? | `pyslang_get_diagnostics` |

Tool counts across the 25 local scalar cases:

| MCP function | Cases |
|---|---:|
| `pyslang_get_diagnostics` | 7 |
| `pyslang_find_symbol` | 5 |
| `pyslang_describe_design_unit` | 4 |
| `pyslang_get_hierarchy` | 3 |
| `pyslang_dump_syntax_tree_summary` | 2 |
| `pyslang_preprocess_files` | 2 |
| `pyslang_get_project_summary` | 1 |
| `pyslang_list_design_units` | 1 |

## Skill Tool-Sequencing Smoke

The `pyslang-verilog-context` eval smoke checks whether expected compiler-backed
tools are selected for representative prompt files. It is separate from the
100-case exact-answer score.

| Prompt case | Prompt file | Expected MCP functions |
|---|---|---|
| `single-file-design-summary` | `single-file-design-summary.md` | `pyslang_parse_files`, `pyslang_get_diagnostics`, `pyslang_list_design_units`, `pyslang_describe_design_unit` |
| `filelist-hierarchy-sync-fifo` | `filelist-hierarchy-sync-fifo.md` | `pyslang_parse_filelist`, `pyslang_get_diagnostics`, `pyslang_list_design_units`, `pyslang_get_hierarchy`, `pyslang_describe_design_unit` |
| `symbol-lookup-apb-timer` | `symbol-lookup-apb-timer.md` | `pyslang_parse_filelist`, `pyslang_get_diagnostics`, `pyslang_find_symbol`, `pyslang_describe_design_unit` |
| `compile-diagnostic-triage` | `compile-diagnostic-triage.md` | `pyslang_parse_files`, `pyslang_get_diagnostics` |
| `clean-frontend-functional-bug` | `clean-frontend-functional-bug.md` | `pyslang_parse_filelist`, `pyslang_get_diagnostics`, `pyslang_get_hierarchy`, `pyslang_find_symbol` |
| `coding-change-with-recheck` | `coding-change-with-recheck.md` | `pyslang_parse_files`, `pyslang_get_diagnostics`, `pyslang_describe_design_unit` |
| `asic-filelist-path-context` | `asic-filelist-path-context.md` | `pyslang_parse_filelist`, `pyslang_get_diagnostics`, `pyslang_get_hierarchy`, `pyslang_describe_design_unit` |
| `cdc-boundary-warning` | `cdc-boundary-warning.md` | `pyslang_parse_files`, `pyslang_get_diagnostics`, `pyslang_describe_design_unit` |
| `web-ibex-counter-summary` | `web-ibex-counter-summary.md` | `pyslang_parse_files`, `pyslang_get_diagnostics`, `pyslang_describe_design_unit`, `pyslang_dump_syntax_tree_summary` |
| `web-picorv32-inventory` | `web-picorv32-inventory.md` | `pyslang_parse_files`, `pyslang_get_diagnostics`, `pyslang_list_design_units`, `pyslang_describe_design_unit`, `pyslang_find_symbol` |
| `web-axis-register-handshake` | `web-axis-register-handshake.md` | `pyslang_parse_files`, `pyslang_get_diagnostics`, `pyslang_describe_design_unit`, `pyslang_find_symbol` |
| `web-common-cells-counter-hierarchy` | `web-common-cells-counter-hierarchy.md` | `pyslang_parse_files`, `pyslang_get_diagnostics`, `pyslang_list_design_units`, `pyslang_get_hierarchy`, `pyslang_describe_design_unit` |

The smoke report currently covers 47 expected MCP tool calls across these 12
prompt cases.
