# Skill + MCP vs Pure LLM Eval Plan

## Goal

Test whether `pyslang-verilog-context` plus `pyslang-mcp` improves real agent
behavior compared with model-only and text-tool baselines.

This is an agent capability eval. It should grade final answers, tool behavior,
patches, and overclaiming. It is not enough to prove that `pyslang-mcp` tools can
run successfully.

## Eval Arms

Run every task with the same model, timeout, prompt, fixture corpus, and scoring
rubric.

1. Pure LLM
   - No shell tools.
   - No MCP tools.
   - No skill.
   - Prompt includes only the task and any provided source text/snippets.
   - Measures model-only HDL reasoning.

2. Text-Tools Agent
   - Allow normal local file tools such as `rg`, `sed`, `cat`, and edits when
     the task requires coding.
   - No `pyslang-mcp`.
   - No `pyslang-verilog-context` skill.
   - Measures the practical baseline for a normal coding agent.

3. MCP-Only Agent
   - Allow `pyslang-mcp`.
   - Do not load `pyslang-verilog-context`.
   - Measures whether the tool is discoverable and useful without procedural
     skill guidance.

4. Skill + MCP Agent
   - Load `pyslang-verilog-context`.
   - Allow `pyslang-mcp`.
   - Measures whether the skill improves tool selection, sequencing, evidence
     quality, and honesty.

## Task Categories

Use tasks where compiler-backed context should matter.

- Diagnostics triage:
  unresolved symbols, syntax errors, missing packages, bad filelist order, or
  missing include directories.

- Filelist/include/define resolution:
  nested `.f` files, `+incdir+`, `-I`, `+define+`, and unsupported directives.

- Design-unit inventory:
  identify modules, interfaces, packages, and likely tops.

- Port and interface summaries:
  summarize parameters, ports, reset behavior, clocking, and interface intent.

- Hierarchy extraction:
  identify child instances and top-level instance trees.

- Symbol lookup:
  find declaration and reference evidence for important signals, parameters,
  state variables, or instances.

- RTL patch tasks:
  make a scoped RTL change and re-run frontend diagnostics afterward.

- Clean-frontend functional bug tasks:
  use examples that parse cleanly but contain intentional behavioral bugs. The
  correct answer should distinguish clean diagnostics from correctness proof.

- Boundary tasks:
  CDC, RDC, lint, reset, and timing-style prompts where `pyslang-mcp` can provide
  structural evidence but must not be presented as signoff.

## Corpus Strategy

Use public upstream RTL as smoke and regression coverage, not as the main
scoring corpus. Public examples may appear in model pretraining.

For scored evals, prefer:

- private/local fixtures
- generated but realistic RTL
- mutated public examples
- renamed modules and signals
- injected bugs with known ground truth
- filelist/include/define traps

Keep public examples in the suite because they prove compatibility with real
style and scale, but do not overinterpret public-example accuracy.

### Current Corpus Snapshot

The 2026-05-23 local run uses two layers:

- 25 mixed local/generated/public cases from the existing benchmark harness.
  These include diagnostics, hierarchy, project loading, symbol references,
  type binding, syntax, preprocessing, interface summaries, and five RTL
  coding/bug-audit cases with known answers.
- 75 additional real public RTL files cloned under
  `reports/real_examples_75/repos/`. These are used as a compatibility and
  frontend-reading stress set, not as the main proof of agent reasoning quality.

The 75 public files were drawn from:

| Repo | Commit | License | Cases |
|---|---|---|---:|
| `lowrisc-ibex` | `9742d89` | Apache-2.0 | 15 |
| `pulp-common-cells` | `63e1b67` | Solderpad-0.51 | 15 |
| `verilog-axis` | `48ff7a7` | MIT | 15 |
| `pulp-axi` | `e286bb1` | Solderpad-0.51 | 15 |
| `pulp-register-interface` | `d6e1d4c` | Solderpad-0.51 | 14 |
| `picorv32` | `87c89ac` | ISC | 1 |

## Scoring

Grade final outputs and transcripts.

Final-answer criteria:

- correct answer for the task
- correct files, modules, ports, signals, and instances identified
- correct diagnostics reported
- correct hierarchy or symbol relationships
- no invented files, signals, modules, or tool results
- no simulation, synthesis, formal, CDC/RDC, timing, or lint signoff claims from
  `pyslang-mcp`
- clear statement of limitations when evidence is incomplete

Tool-behavior criteria:

- uses `pyslang_parse_filelist` when a filelist is provided
- uses `pyslang_parse_files` for explicit source sets
- checks `pyslang_get_diagnostics` before structural claims
- uses `pyslang_list_design_units` before describing unknown units
- uses `pyslang_get_hierarchy` for hierarchy questions
- uses `pyslang_find_symbol` for declaration/reference questions
- uses `pyslang_preprocess_files` for include/define questions
- re-runs diagnostics after RTL edits when feasible

Patch criteria for coding tasks:

- patch is scoped to the request
- patch preserves existing interface intent unless asked otherwise
- post-edit diagnostics are no worse, or any new issue is explained
- no unrelated rewrites

## Metrics

Track:

- answer accuracy by task category
- hallucination and overclaim rate
- diagnostic detection rate
- hierarchy accuracy
- symbol lookup accuracy
- correct tool-use rate
- patch success rate
- post-edit diagnostic status
- runtime
- tool-call count
- token cost
- correct uncertainty or limitation statements

The most useful comparisons are:

```text
Text-Tools Agent vs MCP-Only Agent
MCP-Only Agent vs Skill + MCP Agent
Text-Tools Agent vs Skill + MCP Agent
```

Pure LLM remains a lower-bound baseline, but the practical product question is
whether the skill improves a normal coding agent's HDL work.

## Harness Shape

Represent each eval as structured data:

```json
{
  "id": "symbol-lookup-apb-timer",
  "fixture_root": "fixtures/pyslang-mcp-examples/reference/ip/apb_timer",
  "prompt": "Find where irq_o is declared and referenced.",
  "modes": ["pure_llm", "text_tools", "mcp_only", "skill_mcp"],
  "golden": {
    "must_mention": ["irq_o", "timer_core"],
    "must_not_claim": ["simulation", "formal proof", "CDC signoff"],
    "expected_tools": ["pyslang_parse_filelist", "pyslang_find_symbol"]
  }
}
```

For each mode, save:

- rendered prompt
- transcript
- tool calls
- final answer
- patch diff, if any
- diagnostics before and after edits
- grader result

Run each task in a clean temporary copy or worktree to avoid cross-mode
contamination.

## Grading Strategy

Use deterministic checks first:

- expected tool calls present or absent by mode
- required strings/entities mentioned
- forbidden claims absent
- diagnostics match expected counts or severities
- patch applies and diagnostics rerun

Then use an LLM judge only for semantic quality categories that are hard to
encode, such as explanation clarity or whether a limitation statement is
adequate. Keep the judge blind to the mode name when possible.

## Verification Strategy

The current local verification strategy is deterministic and reproducible:

1. Validate eval fixture paths and prompt metadata:

   ```text
   .venv/bin/python skills/pyslang-verilog-context/scripts/validate_eval_fixtures.py
   ok: 12 cases, 7 fixture sources
   ```

2. Run the repo test suite before interpreting eval results:

   ```text
   .venv/bin/python -m pytest
   37 passed in 3.40s
   ```

3. Run the plan-specific skill/tool-sequencing harness:

   ```text
   .venv/bin/python skills/pyslang-verilog-context/scripts/run_comparison_evals.py
   ```

   This checks that the skill path invokes the expected compiler-backed tools
   for parse mode, diagnostics, design-unit discovery, hierarchy, symbol lookup,
   syntax summary, and coding-change recheck discipline.

4. Run the broader 25-case scalar benchmark:

   ```text
   .venv/bin/python scripts/run_mcp_comparison.py \
     --output-dir reports/mcp_comparison_comprehensive_20260523
   ```

   This compares text/no-skill, MCP/no-skill, and skill+MCP arms on exact
   scalar answers.

5. Run the 75-case real public RTL extension:

   ```text
   .venv/bin/python reports/real_examples_75/run_real75_comparison.py
   ```

   This cycles through frontend diagnostic status, design-unit inventory, and
   first design-unit port count across real public RTL files.

6. Verify report-generation code is syntactically valid:

   ```text
   .venv/bin/python -m py_compile reports/real_examples_75/run_real75_comparison.py
   ```

For now, these runs are deterministic harness checks, not a blind autonomous
LLM-judge eval. The next verification step should add saved agent transcripts,
actual patch diffs for RTL edit tasks, and blind grading of overclaiming and
limitation statements.

## Current Results

2026-05-23 results:

| Benchmark | Text/no skill | MCP/no skill | Skill + MCP |
|---|---:|---:|---:|
| Existing 25-case benchmark | 13/25 | 20/25 | 25/25 |
| Added 75 real public RTL cases | 47/75 | 75/75 | 75/75 |
| Combined 100 cases | 60/100 | 95/100 | 100/100 |

Combined grades:

| Arm | Correct | Accuracy | Grade |
|---|---:|---:|---|
| Text/no skill | 60/100 | 60% | C- |
| MCP/no skill | 95/100 | 95% | A- |
| Skill + MCP | 100/100 | 100% | A |

Interpretation:

- `pyslang-mcp` is the main differentiator for compiler/frontend facts such as
  diagnostics, semantic symbol references, type binding, and file/project
  loading.
- `pyslang-verilog-context` adds measurable value when task success depends on
  sequencing and discipline: check diagnostics before structural claims, use the
  right compiler-backed query, and avoid signoff overclaims.
- The RTL coding/bug-audit cases show the clearest skill-specific delta:
  text/no-skill and MCP/no-skill were both 0/5, while skill+MCP was 5/5.
  MCP proved frontend context; the skill/rule context supplied the RTL audit
  reasoning.

## Acceptance Criteria

The `Skill + MCP` arm should show:

- higher diagnostic and hierarchy accuracy than text tools alone
- better symbol evidence than text search alone
- lower overclaim rate than MCP-only
- higher correct-tool sequencing than MCP-only
- equal or better patch success rate than text tools
- explicit limitations for clean-frontend functional bug and signoff-boundary
  tasks

If `MCP-Only` performs the same as `Skill + MCP`, the skill is too verbose,
unnecessary, or not teaching the agent anything measurable. If `Skill + MCP`
performs worse, tighten the skill around decision points and tool sequencing.
