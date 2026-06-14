---
name: pyslang-verilog-context
description: >
  Use pyslang-mcp for compiler-backed Verilog and SystemVerilog context. Trigger
  this skill for RTL, HDL, Verilog, SystemVerilog, module, interface, package,
  .sv, .svh, .v, .vh, or .f filelist analysis, review, debugging, coding,
  refactoring, hierarchy inspection, diagnostics triage, symbol lookup,
  include/define investigation, and design-unit summaries. Skip it for unrelated
  languages or trivial text searches where rg is sufficient.
---

# pyslang-verilog-context

Use `pyslang-mcp` as read-only compiler-backed context for Verilog and
SystemVerilog work. Keep normal file editing outside the MCP tools.

## First Decision

Use `pyslang-mcp` when the answer depends on any of these:

- parse or semantic diagnostics
- filelist expansion, include dirs, or defines
- module, interface, or package inventory
- ports, declarations, child instances, or hierarchy
- declaration/reference lookup
- syntax-shape or preprocessing metadata
- RTL edits that should preserve an existing compile context

Use direct file reads and `rg` first for tiny lexical questions, comments,
renames, or incomplete snippets where a compiler frontend cannot add much.

## Workflow

1. Establish the HDL input boundary.
   - Prefer user-provided `project_root`, files, filelist, include dirs,
     defines, and top modules.
   - Otherwise infer the smallest conservative project root that contains the
     source set.
   - Keep all paths under `project_root`.

2. Load the project.
   - Use `pyslang_parse_filelist` for `.f` inputs.
   - Use `pyslang_parse_files` for explicit `.sv`, `.svh`, `.v`, or `.vh`
     inputs.
   - Pass known `include_dirs`, `defines`, and `top_modules`; do not invent
     them when the repo does not provide them.

3. Check diagnostics early.
   - Call `pyslang_get_diagnostics` before making structural claims.
   - Treat parse or semantic errors as primary evidence and explain how they
     limit downstream analysis.
   - Do not claim the RTL is functionally correct because diagnostics are clean.

4. Ask focused follow-up questions.
   - Use `pyslang_list_design_units` to discover modules, interfaces, and
     packages.
   - Use `pyslang_describe_design_unit` for ports, declarations, and child
     instances.
   - Use `pyslang_get_hierarchy` for instance tree questions.
   - Use `pyslang_find_symbol` for declarations and references.
   - Use `pyslang_summarize_diagnostics_by_code` before scanning long raw
     diagnostics in large RTL projects.
   - Use `pyslang_find_member` when the question is local to one design unit
     and `pyslang_find_symbol` is too broad.
   - Use `pyslang_get_assignments` for "what drives this signal" or "where is
     this signal used on the RHS" questions.
   - Use `pyslang_get_instance_connections` when one instance's port bindings
     are needed without a full hierarchy dump.
   - Use `pyslang_trace_connectivity` for bounded structural tracing through
     assignments and instance port bindings.
   - Use `pyslang_preprocess_files` for include/define questions.
   - Use `pyslang_dump_syntax_tree_summary` for syntax-shape questions.
   - Use `pyslang_get_project_summary` when a compact overview is enough.

5. Answer with evidence.
   - Name the analyzed files or filelist.
   - Summarize relevant tool results and limitations.
   - Separate compiler evidence from text-grounded reasoning.
   - For edits, patch files normally, then re-run diagnostics when feasible.

## Coding Discipline

Before modifying existing RTL, collect enough compiler context to avoid breaking
the local design shape:

- current ports, parameters, packages, and declared names
- child instances and hierarchy when interfaces are involved
- diagnostics before the edit

After editing, run the same parse mode again and report diagnostics. If
`pyslang-mcp` is unavailable, say so and use text-grounded checks instead.

## Limits

`pyslang-mcp` is not a simulator, synthesizer, linter replacement, CDC/RDC
signoff tool, timing signoff tool, waveform analyzer, or formal engine.

Clean frontend diagnostics mean the analyzed source set parsed and elaborated
under this frontend. They do not prove behavioral correctness, timing closure,
CDC safety, reset safety, or synthesis quality.

`pyslang_trace_connectivity` is structural frontend evidence only. It does not
prove functional behavior, complete fanin/fanout, CDC/RDC safety,
multiple-driver cleanliness, synthesis quality, or timing closure.

The MCP tools are read-only. Never present them as the mechanism that edits,
formats, simulates, or synthesizes RTL.

## Eval Assets

Use `evals/manifest.json` and `scripts/validate_eval_fixtures.py` when updating
this skill. The eval corpus includes local fixtures and public upstream HDL
examples with preserved source provenance.
