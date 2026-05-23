# pyslang-verilog-context Skill Plan

## Objective

Create a reusable Codex skill that makes Verilog and SystemVerilog work
compiler-grounded by default when `pyslang-mcp` is available.

The skill should tell an agent when and how to use `pyslang-mcp` for HDL
analysis, review, debugging, and coding tasks. It should improve evidence
quality without overstating what the server can prove.

## Skill Boundary

The skill belongs in this repository because it is tightly paired with the
`pyslang-mcp` tool surface, examples, limits, and release cycle.

In scope:

- Parse explicit Verilog/SystemVerilog files or filelists before reasoning when
  compiler-backed context is useful.
- Use diagnostics, design-unit inventory, hierarchy, symbol lookup, syntax
  summaries, preprocessing metadata, and project summaries as evidence.
- Ground RTL coding changes by checking existing declarations, packages,
  includes, hierarchy, and diagnostics before editing.
- Distinguish compiler frontend cleanliness from functional correctness.
- Fall back to file reading and `rg` when the source set is partial, the MCP
  server is unavailable, or the user asks for a tiny text-only task.

Out of scope:

- Simulation, synthesis, timing signoff, CDC/RDC signoff, waveform analysis, or
  equivalence checking.
- Claiming that zero `pyslang` diagnostics means the design is bug-free.
- Editing RTL through MCP tools. `pyslang-mcp` remains read-only.
- Hard-coding behavior for proprietary tools or vendor MCP servers.

## Proposed Directory

```text
skills/pyslang-verilog-context/
  PLAN.md
  SKILL.md                         # created during implementation
  agents/openai.yaml               # generated during implementation
  references/
    tool-workflows.md              # optional detailed call patterns
    limitations.md                 # optional scope and non-goals
  scripts/
    detect_hdl_inputs.py           # optional helper for files/filelists/tops
    validate_eval_fixtures.py      # eval manifest and fixture path checker
    run_comparison_evals.py        # text-only versus pyslang evidence runner
  evals/
    manifest.json
    prompts/
    fixtures/
```

Only create reference or script files that remain useful after the first
implementation pass. Keep `SKILL.md` short enough to load every time the skill
triggers.

## Trigger Contract

The final `SKILL.md` frontmatter should trigger on:

- Verilog, SystemVerilog, RTL, HDL, module, interface, package, `.sv`, `.svh`,
  `.v`, `.vh`, or `.f` filelist work.
- Requests to analyze, review, summarize, debug, patch, refactor, or generate
  Verilog/SystemVerilog.
- Requests involving parse errors, semantic diagnostics, hierarchy, module
  ports, instance trees, declarations, references, include paths, defines, or
  filelists.

The description should also say to skip the skill for unrelated languages and
for trivial text searches where `rg` is clearly sufficient.

## Core Agent Workflow

1. Determine the HDL project boundary.
   - Prefer a user-provided `project_root`.
   - Otherwise infer a conservative root from the repo and the source or
     filelist paths.
   - Keep all paths inside the project root.

2. Choose the first evidence call.
   - Use `pyslang_parse_filelist` when a `.f` file is provided or discovered.
   - Use `pyslang_parse_files` for explicit source files.
   - Include `include_dirs`, `defines`, and `top_modules` only when known or
     inferable from local files.

3. Check diagnostics before deeper reasoning.
   - Call `pyslang_get_diagnostics`.
   - Treat diagnostics as primary evidence for parse/elaboration problems.
   - Continue carefully when diagnostics are clean, because behavioral bugs can
     remain.

4. Ask focused semantic questions.
   - Use `pyslang_list_design_units` for inventory.
   - Use `pyslang_describe_design_unit` for ports, declarations, and instances.
   - Use `pyslang_get_hierarchy` when instance relationships matter.
   - Use `pyslang_find_symbol` for declarations and references.
   - Use `pyslang_preprocess_files` for include/define questions.
   - Use `pyslang_dump_syntax_tree_summary` for syntax-shape questions.

5. Produce an evidence-grounded answer.
   - Name which files or filelist were analyzed.
   - Summarize relevant diagnostics and tool evidence.
   - State limitations plainly.
   - For code edits, patch the files normally, then re-run relevant diagnostics
     when feasible.

## Script Candidates

Add scripts only if they remove repeated work:

- `detect_hdl_inputs.py`: scan a repo subtree for candidate `.f` filelists,
  source files, include dirs, top-module names, and obvious compile roots. It
  should emit JSON for use by an agent, not mutate files.
- `validate_eval_fixtures.py`: load `evals/manifest.json` and check referenced
  prompts, fixture roots, source files, filelists, expected evidence, and pass
  criteria.
- `run_comparison_evals.py`: run manifest cases in text-only baseline mode and
  skill-guided `pyslang-mcp` evidence mode, then write comparison reports under
  `evals/reports/`.

Do not add a script that duplicates the MCP server's own analysis logic.

## Eval Strategy

The evals should measure whether a fresh agent:

- Chooses `pyslang-mcp` when HDL semantic context matters.
- Starts with parse/filelist evidence before making structural claims.
- Uses the right follow-up tool for hierarchy, symbols, preprocessing, or
  diagnostics.
- Does not claim simulation, synthesis, CDC/RDC/timing signoff, or functional
  proof from `pyslang-mcp`.
- Handles clean frontend diagnostics and intentional functional bugs as
  different categories.
- Falls back gracefully when MCP evidence is incomplete.

The seed eval corpus is under `evals/fixtures/`:

- `asic-ai-workflows/`: copied HDL and filelist fixtures from
  `/home/arik/projects/asic-ai-workflows/datasets/fixtures`.
- `pyslang-mcp-examples/`: copied HDL corpus from this repository's
  `examples/hdl` tree.
- `pyslang-mcp-tests/`: copied compact parser fixtures from this repository's
  `tests/fixtures`, used for diagnostic-negative coverage.
- `web/`: copied public upstream HDL examples from lowRISC Ibex, YosysHQ
  PicoRV32, Alex Forencich verilog-axis, and PULP common_cells.

The initial eval manifest is `evals/manifest.json`. Each case points to a
prompt file, fixture root, intended tool evidence, and pass criteria. These are
prompt-level evals first; a later harness can execute them by running an agent
with this skill enabled and grading the transcript plus output.

## Initial Eval Cases

1. `single-file-design-summary`
   - Verifies single-file parse, diagnostics, module inventory, and concise
     design summary.

2. `filelist-hierarchy-sync-fifo`
   - Verifies filelist handling, include directories, package presence, and
     hierarchy extraction on a small IP.

3. `symbol-lookup-apb-timer`
   - Verifies declaration/reference lookup and scoped explanation in a bus
     wrapper plus core project.

4. `compile-diagnostic-triage`
   - Verifies diagnostics are reported as compiler evidence and not hidden by
     a prose-only review.

5. `clean-frontend-functional-bug`
   - Verifies the agent does not equate clean diagnostics with functional
     correctness.

6. `coding-change-with-recheck`
   - Verifies the agent gathers existing compiler context before proposing or
     making an RTL edit, then reruns diagnostics.

7. `asic-filelist-path-context`
   - Verifies copied `asic-ai-workflows` filelist fixtures work as independent
     eval roots.

8. `cdc-boundary-warning`
   - Verifies the skill can assist CDC-related review with structural evidence
     while refusing to present `pyslang-mcp` as CDC signoff.

9. `web-ibex-counter-summary`
   - Verifies real upstream SystemVerilog module analysis.

10. `web-picorv32-inventory`
   - Verifies large single-file Verilog inventory and symbol lookup.

11. `web-axis-register-handshake`
   - Verifies AXI Stream interface analysis and symbol evidence.

12. `web-common-cells-counter-hierarchy`
   - Verifies real multi-file SystemVerilog hierarchy analysis.

## Implementation Milestones

1. Seed this plan and eval fixtures.
2. Draft `SKILL.md` with concise trigger-oriented frontmatter and procedural
   body.
3. Add `agents/openai.yaml` using the skill-creator generator.
4. Add `detect_hdl_inputs.py` only if manual eval use shows repeated input
   discovery friction.
5. Add a lightweight CI hook for `scripts/validate_eval_fixtures.py` and the
   non-mutating comparison eval smoke subset.
6. Forward-test the skill on at least the eight initial prompt cases.
7. Tighten `SKILL.md` based on failures, especially false claims of proof or
   missed MCP usage.
8. Decide whether to package this skill as repo documentation only, a
   copy-installable skill, or both.

## Acceptance Criteria

- The skill triggers reliably for Verilog/SystemVerilog analysis and coding
  requests.
- A fresh agent can choose the correct `pyslang-mcp` call sequence from the
  skill alone.
- Eval fixtures include single-file, multi-file, filelist, include, package,
  hierarchy, symbol, clean-bug, and diagnostic-error scenarios.
- Eval outputs cite tool evidence and limitations.
- The skill does not broaden `pyslang-mcp` beyond read-only semantic analysis.
- The skill remains small enough to be loaded routinely without crowding the
  task context.
