# Maximum-Coverage Plan for `pyslang-mcp`

This document lays out how `pyslang-mcp` evolves from a narrow V1 surface
(10 tools) into a broadly useful HDL-analysis server (~40 tools across 10
namespaces). The target is that any semantic question `pyslang` can
answer has a named tool, a stable schema, and an efficient reverse-index
path — so an agent wired to this MCP is strictly better off than one
invoking `pyslang` via ad-hoc Python.

Companion documents:

- [`../pyslang-mcp-plan.md`](../pyslang-mcp-plan.md) — original V1 scope
- [`./architecture.md`](./architecture.md) — current microarchitecture
- [`../REMOTE_DEPLOYMENT.md`](../REMOTE_DEPLOYMENT.md) — hosted-deployment direction

## Framing

Today's 10 tools cover a single agent loop: load → diagnose → inventory
→ walk → find → summarize. That is fine for project overviews, but
every second-order question falls off the edge:

- "What's the resolved type of signal X?"
- "Where is module Y instantiated?"
- "What drives port P on instance I?"
- "Does this generate branch elaborate?"
- "Give me the canonical preprocessed text."

Each of those sends the agent to `python -c "import pyslang; …"` — and
the MCP stops being load-bearing.

**Goal:** any semantic question `pyslang` can answer should have a named
tool, grouped by domain, backed by reverse indices so chained queries
stay cheap. Target surface: **~40 tools across 10 namespaces**, roughly
4× today's.

## Real-World Benchmark Observation (amendment)

On a first real-project benchmark (two files of a production RTL design,
one "is this signal terminated?" question):

| Approach | Tool calls | Wall-clock |
|---|---|---|
| Plain LLM + grep | ~8 | ~5s |
| `pyslang-mcp` | 3 (`parse_files`, `find_symbol`, `describe_design_unit`) | ~94s (45 + 37 + 12) |

Grep was ~20× faster for that specific question. Two things came out of
the timing:

1. **The 37s `find_symbol` and 12s `describe_design_unit` are not
   elaboration cost.** They are the per-call AST walk
   (`compilation.getRoot().visit(...)` matching every node against
   query/name/hierarchical_path/lexical_path) and `symbol.syntax.to_json()`
   materialization. Even on a warm cache, today's implementation is O(N)
   in AST size **per query**.
2. **The existing cache only helps when callers re-use identical
   project args.** Any drift in `files`/`filelist`/`include_dirs` across
   a session produces a fresh `project_hash` and a full re-elaboration.

Grep wins by design on point lookups with known locality — that's fine
and unavoidable. The actionable finding is that the MCP is paying O(N)
algorithmic cost on **its own natural use cases** (whole-project symbol
and reference queries). Reverse indices and session-scoped project
handles are therefore a prerequisite to M6-era tool expansion, not a
later performance polish. This amendment reflects that ordering change.

## Design Principles

1. **Schema-first.** Every tool has a Pydantic input and output model;
   every result is composable with another tool via stable IDs.
2. **Namespaced tool names.** `pyslang_parse_*`, `pyslang_diag_*`,
   `pyslang_hier_*`, `pyslang_sym_*`, `pyslang_type_*`, `pyslang_pp_*`,
   `pyslang_elab_*`, `pyslang_proc_*`, `pyslang_sva_*`, `pyslang_cov_*`,
   `pyslang_cfg_*`, `pyslang_query_*`. Agents pick from groups.
3. **Reverse-indexed.** One pass after `build_analysis` produces:
   `name→[decls]`, `location→node`, `symbol→[drivers]`,
   `symbol→[loads]`, `module→[instantiations]`, `type→[uses]`. Stored on
   `AnalysisBundle`. Every lookup becomes O(1) or O(log n).
4. **Composable URIs.** Tools return opaque IDs like
   `pyslang://project/<config_hash>/symbol/<hier_path>` that flow into
   later tool calls without re-parsing.
5. **Honest surfaces.** If `pyslang` cannot do something cleanly, say so
   in the tool description — never silently produce lossy output.
6. **Degraded-state visibility.** When parse or elaboration hits
   unresolved cross-module references, report it in every affected
   tool's response so the agent knows its downstream reasoning is
   based on incomplete analysis.

## Target Tool Surface, by Tier

### Tier 0 — Infrastructure prerequisite (M6)

No new tools. This milestone is the index and session plumbing every
later milestone depends on. Shipping it first is what turns
`find_symbol` from seconds to milliseconds and makes the rest of the
plan affordable.

**Reverse indices built after `build_analysis`:**

- `name→[decls]` — exact and case-insensitive name lookup
- `location→node` — file/line/col reverse lookup into the AST
- `symbol→[references]` — every AST-accurate reference hit, pre-computed
- `symbol→[drivers]` / `symbol→[loads]` — driver/load edges by
  procedural analysis
- `module→[instantiations]` — reverse map for "who instantiates X"
- `type→[uses]` — where a type alias or struct is referenced

**Symbol URI scheme:**

- Opaque string IDs: `pyslang://project/<config_hash>/symbol/<hier_path>`
- Include the config hash so stale URIs from a previous compilation
  cannot silently resolve.
- Every tool that currently takes a `symbol_path` also accepts a URI;
  tools return URIs alongside hierarchical paths.

**Per-tool-args cache:**

- Layer inside `AnalysisCache`:
  `{(project_hash, tool_name, frozen_args): result}`.
- Repeated identical queries become free (important for the common
  agent pattern of "parse → list → describe each unit").

**Prewarm and cache-hit hygiene:**

- A `get_project_summary` or `parse_filelist` call at session start
  prewarms the bundle.
- Tool descriptions explicitly state that identical `files`/`filelist`
  args across a session are required for cache hits.
- A new `pyslang_query_index_status` tool (ships with M12) exposes
  bundle freshness, cache hit rate, and index build time so agents can
  plan their call sequence.

**Degraded-state signal:**

- Every tool response carries a `project_status` field with values
  `ok` / `degraded` / `incomplete` plus an `unresolved_references`
  count.
- When the parse produces significant cross-module errors (the
  real-world benchmark had 34), agents see a loud `incomplete` status
  instead of silently consuming an empty `ports: []` as ground truth.

### Tier A — Symbol and type resolution (M7)

Highest-impact tool additions; covers the most-asked second-order
questions.

**Symbol and type resolution** (6)

- `pyslang_sym_describe(symbol_path)` — declaration, type, attributes
- `pyslang_sym_drivers(symbol_path)` — who writes it
- `pyslang_sym_loads(symbol_path)` — who reads it
- `pyslang_sym_references(symbol_path)` — every AST-accurate reference
- `pyslang_type_resolve(symbol_or_expr)` — canonical type, packed and
  unpacked dimensions
- `pyslang_type_describe(type_name)` — struct members, enum members,
  typedef chain

**Location-driven navigation** (3)

- `pyslang_query_at(file, line, col)` — what symbol or expression lives
  here
- `pyslang_query_goto_def(symbol_path)` — canonical declaration
- `pyslang_query_goto_impl(symbol_path)` — class method body

**Instance and hierarchy depth** (4)

- `pyslang_hier_describe_instance(hier_path)` — resolved parameters,
  all port connections, generate state
- `pyslang_hier_instantiations_of(module_name)` — reverse map
- `pyslang_hier_get_port_connection(hier_path, port)` — per-port detail
- `pyslang_hier_walk(from_path, depth, filters)` — parameterized
  traversal

### Tier B — Source/PP parity and diagnostics depth (M8)

Closes the `preprocess_files` honesty caveat; diagnostics at scale.

**Source and preprocessing** (4)

- `pyslang_pp_get_text(file, [range])` — real preprocessed text, not a
  summary
- `pyslang_pp_macro_expansions(file)` — resolved macro bodies with
  source locations
- `pyslang_pp_include_graph()` — full include dependency graph
- `pyslang_pp_resolve_include(name, from_file)` — which file resolves

**Diagnostics depth** (3)

- `pyslang_diag_filter(code, severity, path)` — server-side filter
- `pyslang_diag_group_by(code|file|severity)` — aggregated buckets
- `pyslang_diag_explain(code)` — `pyslang`-native explanation of a
  diagnostic code

### Tier C — Elaboration semantics (M9)

**Parameters / generate / defparam / bind / config** (6)

- `pyslang_elab_list_generate_blocks(scope)`
- `pyslang_elab_generate_state(hier_path)` — did it elaborate
- `pyslang_elab_parameter_value(hier_path)` — resolved final value
- `pyslang_elab_list_defparams(project)`
- `pyslang_cfg_list_binds(project)`
- `pyslang_cfg_effective_top(project)`

### Tier D — Procedural, assertions (M10)

**Procedural** (4)

- `pyslang_proc_list_blocks(module)` — always_ff / always_comb /
  always_latch / initial / final
- `pyslang_proc_describe(hier_path)` — sensitivity list, assigned
  signals
- `pyslang_proc_sensitivity(hier_path)`
- `pyslang_proc_driven_signals(hier_path)`

**Assertions (SVA)** (3)

- `pyslang_sva_list(scope)` — assert / assume / cover / restrict
- `pyslang_sva_describe(hier_path)` — property and sequence
  decomposition
- `pyslang_sva_disablement(hier_path)` — disable-iff context

### Tier E — Coverage, random, composition (M11, M12)

**Coverage and random** (4 — M11)

- `pyslang_cov_list_covergroups(scope)`
- `pyslang_cov_describe_covergroup(hier_path)`
- `pyslang_cov_list_constraints(class_name)`
- `pyslang_cov_describe_constraint(hier_path)`

**Composition and agent efficiency** (3 — M12)

- `pyslang_query_batch([tool_calls])` — multiple read-only calls in one
  round-trip, shared compilation
- `pyslang_query_index_status()` — index state, cache hit rate, stale
  files — lets an agent plan
- `pyslang_query_explain(hier_path)` — human-readable narrative of what
  is at a path

## Milestones

| # | Milestone | Tools added | Why now |
|---|---|---|---|
| **M6** | Reverse indices + URI scheme + degraded-state signal | 0 (infra) | Prerequisite for every later milestone; real-world benchmark showed today's tools are O(N) per query |
| **M7** | Symbol/type + location nav + hierarchy depth | 13 | #1 gap; unlocks "go to def / type of X / port connections" flows on an index-backed core |
| **M8** | PP parity + diagnostics depth | 7 | Closes `preprocess_files` honesty caveat; diagnostics at scale |
| **M9** | Elaboration semantics | 6 | The questions simulators answer: generate/param/defparam/bind/config |
| **M10** | Procedural + assertions | 7 | Needed for RTL review and verification agents |
| **M11** | Coverage / random / constraints | 4 | Verification-side completeness |
| **M12** | Batch + agent-planning helpers | 3 | Token efficiency at scale |

**Sequencing rationale (amended).** M6 is now infrastructure, not the
symbol/type tools. The real-world benchmark (Framing section) showed
that today's 10-tool surface already loses to grep by ~20× on point
lookups because `find_symbol` and `describe_design_unit` re-walk the
entire AST per call. Adding more tools on top of the same O(N) core
compounds the problem. Ship the reverse indices, URI scheme, and
per-tool-args cache first, let them prove out on the existing 10 tools,
then layer M7's semantic tools on a foundation that makes them cheap.

M8 closes the one explicit README caveat (`preprocess_files`
summary-only). M9 adds the simulator-style questions. M10 and M11 fill
the verification surface. M12 adds composition — meaningful only after
there are enough tools to compose.

## Testing and Evaluation

- Each new tool ships with: Pydantic schema, unit test on the
  `multi_file` fixture, MCP-level test through `server.call_tool`, and
  a golden JSON snapshot.
- `evaluation.xml` grows from 10 to roughly 50 Q/A pairs, with at least
  one question per namespace that requires chaining 2–3 tools (forcing
  reverse-index use).
- The HDL corpus adds fixtures exercising generate blocks, classes,
  SVA, covergroups, interfaces with modports, binds, and configs. The
  APB timer is the seed for M9; a small UVM-ish verification block is
  the seed for M10 and M11.
- **Benchmark fixture added with M6.** A 5k-line SV project with a
  fixed 20-question harness. Measure wall-clock per tool call on cold
  and warm cache. Gate M6 on: cold `parse_filelist` under 2s, warm
  `find_symbol` under 100ms, warm `describe_design_unit` under 100ms,
  index build under 500ms, resident memory under 500MB. Re-run on
  every milestone to prevent regression.

## Non-Goals (scope protection)

- No simulation, synthesis, static timing analysis, or formal.
- No code editing or refactoring (would break read-only discipline).
- No autofix generation.
- No interactive debugger state.
- No re-testing of `pyslang` itself — we wrap, we do not re-validate
  upstream.

## Success Criteria

The MCP earns its keep when every one of these holds:

1. **A CLI agent with `python` + `pyslang` cannot answer a typical
   RTL-analysis question faster than the MCP.** Measured on the 20-
   question benchmark (not point-lookup questions where grep is
   strictly better). The MCP should win at least 15.
2. **Every question in `evaluation.xml` chains 2+ tools.** Single-tool
   answers indicate missing composition.
3. **Cold-query latency on a 5k-line project is under 2s; warm is
   under 100ms.** Without reverse indices this is unreachable — M6
   gates this explicitly.
4. **Degraded state is impossible to miss.** Any response derived from
   a compilation with unresolved cross-module references shows
   `project_status != "ok"`. Tests assert this on a fixture with
   intentional missing dependencies.
5. **At least 3 MCP clients (Claude Desktop, Cursor, Claude Code) ship
   a working config.** Coverage is useless without reach.

## Relationship to Existing Plans

- `pyslang-mcp-plan.md` remains the V1 scope record; this document
  supersedes it from M6 onward.
- `AGENTS.md` V1 tool list is authoritative for the 10 shipped tools.
  As tools in this plan ship, `AGENTS.md` should update alongside.
- `REMOTE_DEPLOYMENT.md` is orthogonal. Hosted mode reuses whichever
  tool surface the local server exposes.

## Changelog

- **2026-04-19 amendment.** Added real-world benchmark observation
  (grep ~20× faster on point lookups because today's tools are O(N)
  per query on a warm cache). Moved the reverse-indices + URI scheme
  work from M10 to M6 so it ships before any new tools. Added the
  degraded-state `project_status` signal, the prewarm guidance, and
  an explicit benchmark fixture gating M6.
