# Verilog MCP Functions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add five read-only MCP tools for Verilog analysis: `pyslang_find_member`, `pyslang_get_assignments`, `pyslang_trace_connectivity`, `pyslang_get_instance_connections`, and `pyslang_summarize_diagnostics_by_code`.

**Architecture:** Extend the existing `analysis.py` core before touching the FastMCP wrapper. The implementation should build richer per-project indexes from the cached `AnalysisBundle`, expose bounded and schema-validated JSON through `server.py`, and keep syntax-derived fallback evidence explicitly labeled where pyslang semantic bindings are unavailable.

**Tech Stack:** Python 3.11+, `pyslang>=10,<11`, official MCP Python SDK `FastMCP`, Pydantic v2 output schemas, pytest, pyright, ruff, existing fixture and eval harnesses.

---

## Scope

Implement these tools:

- `pyslang_find_member`
- `pyslang_get_assignments`
- `pyslang_trace_connectivity`
- `pyslang_get_instance_connections`
- `pyslang_summarize_diagnostics_by_code`

Do not implement `pyslang_parse_generated_cache` in this plan.

## Product Constraints

- Tools remain read-only.
- All caller-provided files, filelists, and include dirs continue through `project_loader.py` root containment.
- Outputs are compact, stable JSON with explicit truncation metadata.
- Every new list-like output has hard bounds enforced in `server.py` and represented in input schemas.
- Cache behavior remains keyed by normalized project config plus tracked file mtimes; new tool results use the existing per-tool cache path.
- Hardware claims stay narrow: these tools provide compiler-front-end structural evidence, not simulation, CDC/RDC, timing, synthesis, formal, or functional correctness proof.
- For syntax-only fallbacks, outputs include `evidence_source: "syntax"` and avoid type/width claims that pyslang did not provide.

## Recommended Delivery Order

1. Diagnostic grouping: lowest risk, immediately useful for large generated caches.
2. Member lookup: fixes the most direct gap and creates shared member/type helpers.
3. Instance connections: uses existing hierarchy records and creates connection normalization.
4. Assignment extraction: adds expression-side symbol collection and assignment indexing.
5. Connectivity tracing: composes connection and assignment indexes into bounded graph traversal.
6. Docs, skill wording, protocol smoke, and full eval validation.

## File Map

- Modify `src/pyslang_mcp/types.py`
  - Add internal dataclasses for indexed members, assignments, connections, and connectivity edges.
  - Extend `AnalysisIndex` with member, assignment, and connectivity indexes.
- Modify `src/pyslang_mcp/analysis.py`
  - Add helper functions for symbol paths, design-unit resolution, expression symbol extraction, member extraction, assignment extraction, instance connection normalization, diagnostics grouping, and graph traversal.
  - Add public core functions for all five new tools.
- Modify `src/pyslang_mcp/schemas.py`
  - Add Pydantic output models for all five new tools.
  - Keep `StrictModel` and `extra="forbid"` behavior.
- Modify `src/pyslang_mcp/server.py`
  - Add public tool names, input argument aliases, max-limit constants, validators, imports, and `@mcp.tool` registrations.
- Modify `README.md`
  - Add tools table entries and short usage examples.
- Modify `AGENTS.md`
  - Add the five implemented tools to the public tool surface.
- Modify `docs/architecture.md`
  - Update module map and extension description from 10 to 15 tools.
- Modify `skills/pyslang-verilog-context/SKILL.md`
  - Teach the skill when to use the new tools.
- Create `tests/fixtures/verilog_debug/project.f`
- Create `tests/fixtures/verilog_debug/verilog_debug.sv`
- Modify `tests/test_analysis.py`
  - Add unit coverage for the core functions.
- Modify `tests/test_server.py`
  - Add tool contract, schema, hard-limit, argument validation, and cache tests.
- Modify `tests/test_mcp_stdio.py`
  - Add the new tools to protocol smoke.
- Modify or add eval prompts under `skills/pyslang-verilog-context/evals/`
  - Only if skill behavior or expected tool evidence changes.

---

### Task 1: Add Shared Fixture For Member, Assignment, Instance, And Trace Queries

**Files:**
- Create: `tests/fixtures/verilog_debug/project.f`
- Create: `tests/fixtures/verilog_debug/verilog_debug.sv`
- Modify: `tests/test_analysis.py`

**ASIC Evidence:**
- Lane: RTL
- Before evidence: `./.venv/bin/python -m py_compile src/pyslang_mcp/analysis.py`
- After evidence: `./.venv/bin/pytest -q tests/test_analysis.py::test_verilog_debug_fixture_baseline`
- Supported claim: The fixture parses and elaborates under pyslang with no diagnostics.
- Unsupported claim: The fixture behavior is functionally correct or timing/CDC clean.

- [x] **Step 1: Create the fixture filelist**

Create `tests/fixtures/verilog_debug/project.f`:

```text
verilog_debug.sv
```

- [x] **Step 2: Create a compact HDL fixture**

Create `tests/fixtures/verilog_debug/verilog_debug.sv`:

```systemverilog
module debug_sink (
  input  logic clk,
  input  logic rst_n,
  input  logic sink_ready_i,
  input  logic response__vld,
  output logic response_pop_fifo__rdy,
  output logic [7:0] observed_data_o
);
  logic local_gate;
  logic [7:0] sampled_data;

  assign local_gate = rst_n & sink_ready_i;
  assign response_pop_fifo__rdy = local_gate & response__vld;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      sampled_data <= 8'h00;
    end else if (response__vld && response_pop_fifo__rdy) begin
      sampled_data <= 8'hA5;
    end
  end

  assign observed_data_o = sampled_data;
endmodule

module debug_stage (
  input  logic clk,
  input  logic rst_n,
  input  logic ctrl_out__rdy,
  output logic ctrl_iut__rdy,
  output logic response__vld,
  output logic [7:0] observed_data_o
);
  logic response_pop_fifo__rdy;
  logic stage_enable;

  assign stage_enable = ctrl_out__rdy & rst_n;
  assign response__vld = stage_enable;
  assign ctrl_iut__rdy = response_pop_fifo__rdy;

  debug_sink u_sink (
    .clk(clk),
    .rst_n(rst_n),
    .sink_ready_i(ctrl_out__rdy),
    .response__vld(response__vld),
    .response_pop_fifo__rdy(response_pop_fifo__rdy),
    .observed_data_o(observed_data_o)
  );
endmodule

module debug_top (
  input  logic clk,
  input  logic rst_n,
  input  logic downstream_ready_i,
  output logic upstream_ready_o,
  output logic response_valid_o,
  output logic [7:0] observed_data_o
);
  logic ctrl_out__rdy;
  logic ctrl_iut__rdy;
  logic response__vld;

  assign ctrl_out__rdy = downstream_ready_i;
  assign upstream_ready_o = ctrl_iut__rdy;
  assign response_valid_o = response__vld;

  debug_stage u_stage (
    .clk(clk),
    .rst_n(rst_n),
    .ctrl_out__rdy(ctrl_out__rdy),
    .ctrl_iut__rdy(ctrl_iut__rdy),
    .response__vld(response__vld),
    .observed_data_o(observed_data_o)
  );
endmodule
```

- [x] **Step 3: Add a baseline fixture test**

Append this test to `tests/test_analysis.py`:

```python
def test_verilog_debug_fixture_baseline() -> None:
    project = load_project_from_filelist(
        project_root=FIXTURES / "verilog_debug",
        filelist="project.f",
        top_modules=["debug_top"],
    )
    bundle = build_analysis(project)

    diagnostics = get_diagnostics(bundle)
    assert diagnostics["project_status"]["status"] == "ok"
    assert diagnostics["summary"]["total"] == 0

    units = list_design_units(bundle)
    assert {"debug_top", "debug_stage", "debug_sink"} <= {
        unit["name"] for unit in units["design_units"]
    }

    hierarchy = get_hierarchy(bundle, max_depth=4)
    assert hierarchy["summary"]["total_instances"] == 3
    assert hierarchy["hierarchy"][0]["name"] == "debug_top"
    assert hierarchy["hierarchy"][0]["children"][0]["name"] == "u_stage"
```

- [x] **Step 4: Run the baseline test**

Run:

```bash
./.venv/bin/pytest -q tests/test_analysis.py::test_verilog_debug_fixture_baseline
```

Expected:

```text
1 passed
```

- [x] **Step 5: Commit the fixture**

```bash
git add tests/fixtures/verilog_debug/project.f tests/fixtures/verilog_debug/verilog_debug.sv tests/test_analysis.py
git commit -m "test: add Verilog debug HDL fixture"
```

---

### Task 2: Add Internal Index Data Types And Bounds

**Files:**
- Modify: `src/pyslang_mcp/types.py`
- Modify: `src/pyslang_mcp/server.py`

**ASIC Evidence:**
- Lane: RTL
- Before evidence: `./.venv/bin/pytest -q tests/test_analysis.py::test_verilog_debug_fixture_baseline`
- After evidence: `./.venv/bin/python -m py_compile src/pyslang_mcp/types.py src/pyslang_mcp/server.py`
- Supported claim: Internal Python types compile and preserve existing analysis behavior.
- Unsupported claim: New MCP tools are functional before later tasks.

- [x] **Step 1: Add index dataclasses**

In `src/pyslang_mcp/types.py`, add these dataclasses below `IndexedReference`:

```python
@dataclass(slots=True)
class IndexedMember:
    """Precomputed design-unit member lookup entry."""

    design_unit: str
    candidates: tuple[str, ...]
    output: dict[str, Any]


@dataclass(slots=True)
class IndexedAssignment:
    """Precomputed assignment lookup entry."""

    design_unit: str
    lhs_candidates: tuple[str, ...]
    rhs_candidates: tuple[str, ...]
    output: dict[str, Any]


@dataclass(slots=True)
class IndexedInstanceConnection:
    """Precomputed instance port-connection entry."""

    instance_path: str
    port_name: str
    candidates: tuple[str, ...]
    output: dict[str, Any]


@dataclass(slots=True)
class ConnectivityEdge:
    """Directed structural edge used by connectivity tracing."""

    source: str
    target: str
    kind: str
    output: dict[str, Any]
```

- [x] **Step 2: Extend `AnalysisIndex`**

In `AnalysisIndex`, add these fields after `references`:

```python
    members_by_design_unit: dict[str, tuple[IndexedMember, ...]]
    assignments_by_design_unit: dict[str, tuple[IndexedAssignment, ...]]
    connections_by_instance_path: dict[str, tuple[IndexedInstanceConnection, ...]]
    connectivity_edges_by_source: dict[str, tuple[ConnectivityEdge, ...]]
    connectivity_edges_by_target: dict[str, tuple[ConnectivityEdge, ...]]
```

- [x] **Step 3: Import new dataclasses in `analysis.py`**

Update the import block in `src/pyslang_mcp/analysis.py`:

```python
from .types import (
    AnalysisBundle,
    AnalysisIndex,
    ConnectivityEdge,
    IndexedAssignment,
    IndexedDeclaration,
    IndexedInstanceConnection,
    IndexedMember,
    IndexedReference,
    ProjectConfig,
)
```

- [x] **Step 4: Add server hard-limit constants**

In `src/pyslang_mcp/server.py`, add these constants near existing `MAX_*` values:

```python
MAX_MEMBER_RESULTS = 1000
MAX_ASSIGNMENT_RESULTS = 1000
MAX_CONNECTION_RESULTS = 1000
MAX_TRACE_DEPTH = 16
MAX_TRACE_EDGES = 1000
MAX_DIAGNOSTIC_GROUPS = 1000
MAX_DIAGNOSTIC_EXAMPLES_PER_GROUP = 20
```

- [x] **Step 5: Run compile check**

Run:

```bash
./.venv/bin/python -m py_compile src/pyslang_mcp/types.py src/pyslang_mcp/analysis.py src/pyslang_mcp/server.py
```

Expected: command exits with status 0.

- [x] **Step 6: Commit the internal type expansion**

```bash
git add src/pyslang_mcp/types.py src/pyslang_mcp/analysis.py src/pyslang_mcp/server.py
git commit -m "refactor: add Verilog debug analysis index types"
```

---

### Task 3: Add Core Helper Functions For Symbols, Design Units, And Expressions

**Files:**
- Modify: `src/pyslang_mcp/analysis.py`
- Modify: `tests/test_analysis.py`

**ASIC Evidence:**
- Lane: RTL
- Before evidence: `./.venv/bin/pytest -q tests/test_analysis.py::test_analysis_over_filelist_fixture`
- After evidence: `./.venv/bin/pytest -q tests/test_analysis.py::test_analysis_over_filelist_fixture tests/test_analysis.py::test_verilog_debug_fixture_baseline`
- Supported claim: Shared helpers preserve existing symbol and hierarchy behavior.
- Unsupported claim: Assignment or connectivity tools are complete before their dedicated tasks.

- [x] **Step 1: Add helper functions for stable symbol metadata**

Add these helpers near `_symbol_candidates` in `src/pyslang_mcp/analysis.py`:

```python
def _symbol_kind_name(symbol: Any) -> str:
    kind = getattr(symbol, "kind", None)
    return kind.name if kind is not None else type(symbol).__name__


def _symbol_hierarchical_path(symbol: Any) -> str:
    return str(getattr(symbol, "hierarchicalPath", getattr(symbol, "name", "")))


def _symbol_lexical_path(symbol: Any) -> str:
    return str(getattr(symbol, "lexicalPath", getattr(symbol, "name", "")))


def _design_unit_from_lexical_path(path: str) -> str | None:
    if not path:
        return None
    cleaned = path.split("::", 1)[0] if "::" in path else path
    return cleaned.split(".", 1)[0] or None


def _symbol_design_unit(symbol: Any) -> str | None:
    lexical = _symbol_lexical_path(symbol)
    from_lexical = _design_unit_from_lexical_path(lexical)
    if from_lexical:
        return from_lexical
    parent_scope = getattr(symbol, "parentScope", None)
    parent_lexical = _symbol_lexical_path(parent_scope) if parent_scope is not None else ""
    return _design_unit_from_lexical_path(parent_lexical)


def _data_type_text(symbol: Any) -> str | None:
    type_obj = getattr(symbol, "type", None)
    if type_obj is None:
        declared_type = getattr(symbol, "declaredType", None)
        type_obj = getattr(declared_type, "type", None)
    text = str(type_obj) if type_obj is not None else ""
    return text or None


def _direction_name(symbol: Any) -> str | None:
    direction = getattr(symbol, "direction", None)
    return getattr(direction, "name", None) if direction is not None else None
```

- [x] **Step 2: Add expression symbol collection**

Add this helper near `_collect_reference_index_entries`:

```python
def _expression_symbol_hits(expression: Any) -> tuple[dict[str, Any], ...]:
    hits: list[dict[str, Any]] = []
    seen: set[str] = set()

    def visit(node: Any) -> bool:
        if type(node).__name__ == "NamedValueExpression" and getattr(node, "symbol", None):
            symbol = node.symbol
            path = _symbol_hierarchical_path(symbol)
            if path and path not in seen:
                seen.add(path)
                hits.append(
                    {
                        "name": getattr(symbol, "name", None),
                        "kind": _symbol_kind_name(symbol),
                        "hierarchical_path": path,
                        "lexical_path": _symbol_lexical_path(symbol),
                    }
                )
        return True

    if expression is not None:
        try:
            expression.visit(visit)
        except Exception:
            visit(expression)
    return tuple(hits)
```

- [x] **Step 3: Add candidate helper for serialized symbol hits**

Add:

```python
def _symbol_hit_candidates(hit: dict[str, Any]) -> tuple[str, ...]:
    return _candidate_tuple(
        (
            hit.get("name"),
            hit.get("hierarchical_path"),
            hit.get("lexical_path"),
            hit.get("kind"),
        )
    )
```

- [x] **Step 4: Add a helper regression test**

Append to `tests/test_analysis.py`:

```python
def test_verilog_debug_symbol_helpers_preserve_existing_index() -> None:
    project = load_project_from_filelist(
        project_root=FIXTURES / "verilog_debug",
        filelist="project.f",
        top_modules=["debug_top"],
    )
    bundle = build_analysis(project)
    assert bundle.index is not None

    declarations = [
        declaration.output["hierarchical_path"]
        for declaration in bundle.index.declarations
    ]
    assert "debug_top.ctrl_out__rdy" in declarations
    assert "debug_top.u_stage.response_pop_fifo__rdy" in declarations
```

- [x] **Step 5: Run focused tests**

Run:

```bash
./.venv/bin/pytest -q tests/test_analysis.py::test_analysis_over_filelist_fixture tests/test_analysis.py::test_verilog_debug_symbol_helpers_preserve_existing_index
```

Expected:

```text
2 passed
```

- [x] **Step 6: Commit helper groundwork**

```bash
git add src/pyslang_mcp/analysis.py tests/test_analysis.py
git commit -m "refactor: add symbol helper groundwork"
```

---

### Task 4: Implement `pyslang_summarize_diagnostics_by_code`

**Files:**
- Modify: `src/pyslang_mcp/analysis.py`
- Modify: `src/pyslang_mcp/schemas.py`
- Modify: `src/pyslang_mcp/server.py`
- Modify: `tests/test_analysis.py`
- Modify: `tests/test_server.py`

**ASIC Evidence:**
- Lane: RTL
- Before evidence: `./.venv/bin/pytest -q tests/test_analysis.py::test_diagnostics_on_broken_fixture`
- After evidence: `./.venv/bin/pytest -q tests/test_analysis.py::test_summarize_diagnostics_by_code_on_broken_fixture tests/test_server.py::test_summarize_diagnostics_by_code_tool`
- Supported claim: Diagnostics are grouped by frontend diagnostic code with bounded examples.
- Unsupported claim: Grouping proves which diagnostics are real design bugs.

- [x] **Step 1: Add schemas**

Add these models to `src/pyslang_mcp/schemas.py` after `DiagnosticsResult`:

```python
class DiagnosticGroup(StrictModel):
    code: str
    severity: str
    count: int
    affected_files_count: int
    affected_design_units_count: int
    unresolved_reference_count: int
    message_samples: list[str]
    examples: list[DiagnosticEntry]
    truncation: TruncationInfo


class DiagnosticGroupSummary(StrictModel):
    total_diagnostics: int
    total_groups: int
    severity_counts: dict[str, int]
    truncation: TruncationInfo


class SummarizeDiagnosticsByCodeResult(StrictModel):
    project_status: ProjectStatus
    project_root: str
    summary: DiagnosticGroupSummary
    groups: list[DiagnosticGroup]
```

- [x] **Step 2: Add core grouping function**

Add this function to `src/pyslang_mcp/analysis.py` after `get_diagnostics`:

```python
def summarize_diagnostics_by_code(
    bundle: AnalysisBundle,
    *,
    max_groups: int = 200,
    max_examples_per_group: int = 3,
) -> dict[str, Any]:
    """Group parse and semantic diagnostics by diagnostic code and severity."""

    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    severity_counts: Counter[str] = Counter()
    total_diagnostics = 0

    for diagnostic in bundle.compilation.getAllDiagnostics():
        total_diagnostics += 1
        entry = _serialize_diagnostic(bundle, diagnostic)
        severity = str(entry["severity"])
        severity_counts[severity] += 1
        code = str(entry["code"])
        key = (code, severity)
        group = grouped.setdefault(
            key,
            {
                "code": code,
                "severity": severity,
                "count": 0,
                "affected_files": set(),
                "affected_design_units": set(),
                "unresolved_reference_count": 0,
                "message_samples": [],
                "examples": [],
            },
        )
        group["count"] += 1
        location = entry.get("location")
        if isinstance(location, dict) and location.get("path"):
            group["affected_files"].add(str(location["path"]))
        for unit in _diagnostic_design_unit_candidates(bundle, location):
            group["affected_design_units"].add(unit)
        message = str(entry["message"])
        if message not in group["message_samples"] and len(group["message_samples"]) < 3:
            group["message_samples"].append(message)
        if _diagnostic_looks_unresolved(entry):
            group["unresolved_reference_count"] += 1
        if len(group["examples"]) < max(max_examples_per_group, 0):
            group["examples"].append(entry)

    groups: list[dict[str, Any]] = []
    for group in grouped.values():
        examples = list(group["examples"])
        groups.append(
            {
                "code": group["code"],
                "severity": group["severity"],
                "count": group["count"],
                "affected_files_count": len(group["affected_files"]),
                "affected_design_units_count": len(group["affected_design_units"]),
                "unresolved_reference_count": group["unresolved_reference_count"],
                "message_samples": list(group["message_samples"]),
                "examples": examples,
                "truncation": _truncation(returned=len(examples), total=group["count"]),
            }
        )

    groups.sort(key=lambda item: (-int(item["count"]), str(item["code"]), str(item["severity"])))
    limited_groups, group_truncation = limit_list(groups, max_items=max_groups)
    return stabilize_json(
        {
            "project_status": _project_status(bundle),
            "project_root": bundle.project.project_root.as_posix(),
            "summary": {
                "total_diagnostics": total_diagnostics,
                "total_groups": len(groups),
                "severity_counts": dict(sorted(severity_counts.items())),
                "truncation": group_truncation,
            },
            "groups": limited_groups,
        }
    )
```

- [x] **Step 3: Add diagnostic helper functions**

Add below `_project_status`:

```python
def _diagnostic_looks_unresolved(entry: dict[str, Any]) -> bool:
    text = f"{entry.get('code', '')} {entry.get('message', '')}".lower()
    return any(
        marker in text
        for marker in (
            "undeclared",
            "unresolved",
            "unknown module",
            "unknown type",
            "could not find",
        )
    )


def _diagnostic_design_unit_candidates(
    bundle: AnalysisBundle,
    location: dict[str, Any] | None,
) -> tuple[str, ...]:
    if not location:
        return ()
    path = location.get("path")
    if not isinstance(path, str):
        return ()
    line = int(location.get("line", 0))
    candidates: list[str] = []
    for record in _analysis_index(bundle).design_unit_records:
        record_location = record.get("location")
        if not isinstance(record_location, dict):
            continue
        if record_location.get("path") == path and int(record_location.get("line", 0)) <= line:
            candidates.append(str(record["name"]))
    return tuple(candidates[-1:])
```

- [x] **Step 4: Wire server imports and tool name**

In `src/pyslang_mcp/server.py`, import the core function and schema:

```python
from .analysis import summarize_diagnostics_by_code as summarize_diagnostics_by_code_core
```

```python
    SummarizeDiagnosticsByCodeResult,
```

Add to `PUBLIC_TOOL_NAMES`:

```python
    "summarize_diagnostics_by_code": f"{TOOL_NAME_PREFIX}summarize_diagnostics_by_code",
```

- [x] **Step 5: Add bounded args**

Add:

```python
MaxDiagnosticGroupsArg = Annotated[
    int,
    Field(
        default=200,
        description="Maximum diagnostic-code groups to return before truncation.",
        json_schema_extra={"minimum": 0, "maximum": MAX_DIAGNOSTIC_GROUPS},
    ),
]
MaxDiagnosticExamplesPerGroupArg = Annotated[
    int,
    Field(
        default=3,
        description="Maximum representative diagnostics to include per group.",
        json_schema_extra={"minimum": 0, "maximum": MAX_DIAGNOSTIC_EXAMPLES_PER_GROUP},
    ),
]
```

- [x] **Step 6: Register the MCP tool**

Add this tool after `get_diagnostics`:

```python
    @mcp.tool(
        name=PUBLIC_TOOL_NAMES["summarize_diagnostics_by_code"],
        annotations=READ_ONLY_ANNOTATIONS,
        description=(
            "Group parse and semantic diagnostics by diagnostic code and severity. Use this for "
            "large large projects where raw diagnostics contain repeated warnings or errors; "
            "results include counts, representative examples, affected-file counts, and "
            "unresolved-reference correlation counts."
        ),
    )
    def summarize_diagnostics_by_code(
        project_root: ProjectRootArg,
        files: OptionalFilesArg = None,
        filelist: OptionalFilelistArg = None,
        include_dirs: IncludeDirsArg = None,
        defines: DefinesArg = None,
        top_modules: TopModulesArg = None,
        max_groups: MaxDiagnosticGroupsArg = 200,
        max_examples_per_group: MaxDiagnosticExamplesPerGroupArg = 3,
    ) -> Annotated[CallToolResult, SummarizeDiagnosticsByCodeResult | ToolErrorResult]:
        return run_project_tool(
            SummarizeDiagnosticsByCodeResult,
            tool_name="summarize_diagnostics_by_code",
            tool_args={
                "max_groups": max_groups,
                "max_examples_per_group": max_examples_per_group,
            },
            project_factory=lambda: resolve_project(
                project_root=project_root,
                files=files,
                filelist=filelist,
                include_dirs=include_dirs,
                defines=defines,
                top_modules=top_modules,
            ),
            callback=lambda bundle: summarize_diagnostics_by_code_core(
                bundle,
                max_groups=bounded_int(
                    "max_groups",
                    max_groups,
                    minimum=0,
                    maximum=MAX_DIAGNOSTIC_GROUPS,
                ),
                max_examples_per_group=bounded_int(
                    "max_examples_per_group",
                    max_examples_per_group,
                    minimum=0,
                    maximum=MAX_DIAGNOSTIC_EXAMPLES_PER_GROUP,
                ),
            ),
        )
```

- [x] **Step 7: Add core tests**

Add imports in `tests/test_analysis.py`:

```python
    summarize_diagnostics_by_code,
```

Append:

```python
def test_summarize_diagnostics_by_code_on_broken_fixture() -> None:
    project = load_project_from_files(
        project_root=FIXTURES / "broken",
        files=["broken.sv"],
    )
    bundle = build_analysis(project)

    summary = summarize_diagnostics_by_code(bundle, max_groups=10, max_examples_per_group=1)

    assert summary["project_status"]["status"] == "incomplete"
    assert summary["summary"]["total_diagnostics"] == 1
    assert summary["summary"]["total_groups"] == 1
    assert summary["groups"][0]["count"] == 1
    assert summary["groups"][0]["unresolved_reference_count"] == 1
    assert len(summary["groups"][0]["examples"]) == 1
```

- [x] **Step 8: Add server tests**

Update `tests/test_server.py` expected models and bounds, then append:

```python
def test_summarize_diagnostics_by_code_tool() -> None:
    payload, is_error = _call_tool_json(
        PUBLIC_TOOL_NAMES["summarize_diagnostics_by_code"],
        {
            "project_root": str(FIXTURES / "broken"),
            "files": ["broken.sv"],
            "max_groups": 10,
            "max_examples_per_group": 1,
        },
    )

    assert not is_error
    assert payload["summary"]["total_diagnostics"] == 1
    assert payload["groups"][0]["count"] == 1
```

- [x] **Step 9: Run focused tests**

Run:

```bash
./.venv/bin/pytest -q tests/test_analysis.py::test_summarize_diagnostics_by_code_on_broken_fixture tests/test_server.py::test_summarize_diagnostics_by_code_tool tests/test_server.py::test_tools_list_exposes_output_schema tests/test_server.py::test_tools_list_exposes_hard_limit_bounds
```

Expected: all selected tests pass.

- [x] **Step 10: Commit diagnostic grouping**

```bash
git add src/pyslang_mcp/analysis.py src/pyslang_mcp/schemas.py src/pyslang_mcp/server.py tests/test_analysis.py tests/test_server.py
git commit -m "feat: summarize diagnostics by code"
```

---

### Task 5: Build Member Index And Implement `pyslang_find_member`

**Files:**
- Modify: `src/pyslang_mcp/analysis.py`
- Modify: `src/pyslang_mcp/schemas.py`
- Modify: `src/pyslang_mcp/server.py`
- Modify: `tests/test_analysis.py`
- Modify: `tests/test_server.py`

**ASIC Evidence:**
- Lane: RTL
- Before evidence: `./.venv/bin/pytest -q tests/test_analysis.py::test_verilog_debug_fixture_baseline`
- After evidence: `./.venv/bin/pytest -q tests/test_analysis.py::test_find_member_generated_nets tests/test_server.py::test_find_member_tool`
- Supported claim: Local ports, variables/nets, parameters, and instances visible to pyslang are queryable by design unit.
- Unsupported claim: Member lookup proves driver/load behavior or functional intent.

- [x] **Step 1: Add member schemas**

Add to `src/pyslang_mcp/schemas.py` after `DescribeDesignUnitResult`:

```python
class MemberRecord(StrictModel):
    name: str
    kind: str
    symbol_kind: str
    design_unit: str
    hierarchical_path: str
    lexical_path: str
    location: Location | None = None
    direction: str | None = None
    data_type: str | None = None
    evidence_source: Literal["semantic", "syntax"]


class FindMemberSummary(StrictModel):
    total: int
    by_kind: dict[str, int]
    truncation: TruncationInfo


class FindMemberResult(StrictModel):
    project_status: ProjectStatus
    design_unit_query: str
    found_design_unit: bool
    ambiguous_design_unit: bool
    design_unit_candidates: list[DesignUnitRecord]
    query: str
    match_mode: Literal["exact", "contains", "startswith"]
    summary: FindMemberSummary
    members: list[MemberRecord]
```

- [x] **Step 2: Add member serialization helper**

Add in `analysis.py`:

```python
def _member_kind(symbol: Any) -> str | None:
    kind_name = _symbol_kind_name(symbol)
    if kind_name == "Port":
        return "port"
    if kind_name == "Instance":
        return "instance"
    if kind_name in {"Variable", "Net"}:
        return "variable"
    if kind_name in {"Parameter", "ParameterSymbol"}:
        return "parameter"
    if kind_name in {"TypeAlias", "TypeAliasType"}:
        return "type"
    return None


def _make_member_entry(bundle: AnalysisBundle, symbol: Any) -> IndexedMember | None:
    design_unit = _symbol_design_unit(symbol)
    kind = _member_kind(symbol)
    name = getattr(symbol, "name", None)
    if not design_unit or not kind or not name:
        return None
    output = {
        "name": str(name),
        "kind": kind,
        "symbol_kind": _symbol_kind_name(symbol),
        "design_unit": design_unit,
        "hierarchical_path": _symbol_hierarchical_path(symbol),
        "lexical_path": _symbol_lexical_path(symbol),
        "location": _serialize_location(bundle, getattr(symbol, "location", None)),
        "direction": _direction_name(symbol),
        "data_type": _data_type_text(symbol),
        "evidence_source": "semantic",
    }
    return IndexedMember(
        design_unit=design_unit,
        candidates=_candidate_tuple(
            (
                output["name"],
                output["kind"],
                output["symbol_kind"],
                output["hierarchical_path"],
                output["lexical_path"],
            )
        ),
        output=output,
    )
```

- [x] **Step 3: Extend `_build_index` collection**

Inside `_build_index`, add local containers before `visit`:

```python
    members_by_design_unit: defaultdict[str, list[IndexedMember]] = defaultdict(list)
    seen_members: set[tuple[str, str, str]] = set()
```

Inside `visit(symbol)`, after reference collection and before returning:

```python
        member_entry = _make_member_entry(bundle, symbol)
        if member_entry is not None:
            key = (
                member_entry.design_unit,
                str(member_entry.output["kind"]),
                str(member_entry.output["hierarchical_path"]),
            )
            if key not in seen_members:
                seen_members.add(key)
                members_by_design_unit[member_entry.design_unit].append(member_entry)
```

When returning `AnalysisIndex`, pass:

```python
        members_by_design_unit={
            key: tuple(sorted(values, key=lambda item: str(item.output["hierarchical_path"])))
            for key, values in members_by_design_unit.items()
        },
        assignments_by_design_unit={},
        connections_by_instance_path={},
        connectivity_edges_by_source={},
        connectivity_edges_by_target={},
```

- [x] **Step 4: Add design-unit resolver**

Add:

```python
def _resolve_design_unit(
    bundle: AnalysisBundle,
    *,
    name: str,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], bool]:
    records = list(_analysis_index(bundle).design_unit_records)
    exact = [record for record in records if record["name"] == name]
    if len(exact) == 1:
        return exact[0], [], False
    suggestions = [
        record
        for record in records
        if _matches_text(
            query=name,
            match_mode="contains",
            candidates={record["name"], record["hierarchical_path"], record["lexical_path"]},
        )
        or str(record["name"]).lower().startswith(name.lower())
    ][:10]
    return None, exact or suggestions, len(exact) > 1
```

- [x] **Step 5: Add `find_member` core function**

Add after `describe_design_unit`:

```python
def find_member(
    bundle: AnalysisBundle,
    *,
    design_unit: str,
    query: str,
    match_mode: MatchMode = "exact",
    include_ports: bool = True,
    include_nets: bool = True,
    include_variables: bool = True,
    include_instances: bool = True,
    include_parameters: bool = True,
    max_results: int = 100,
) -> dict[str, Any]:
    """Find local members inside a specific design unit."""

    selected, candidates, ambiguous = _resolve_design_unit(bundle, name=design_unit)
    if selected is None:
        return stabilize_json(
            {
                "project_status": _project_status(bundle),
                "design_unit_query": design_unit,
                "found_design_unit": False,
                "ambiguous_design_unit": ambiguous,
                "design_unit_candidates": candidates,
                "query": query,
                "match_mode": match_mode,
                "summary": {
                    "total": 0,
                    "by_kind": {},
                    "truncation": _truncation(returned=0, total=0),
                },
                "members": [],
            }
        )

    allowed = set()
    if include_ports:
        allowed.add("port")
    if include_nets or include_variables:
        allowed.add("variable")
    if include_instances:
        allowed.add("instance")
    if include_parameters:
        allowed.add("parameter")

    entries = _analysis_index(bundle).members_by_design_unit.get(str(selected["name"]), ())
    matching: list[dict[str, Any]] = []
    kind_counts: Counter[str] = Counter()
    total = 0
    limit = max(max_results, 0)
    for entry in entries:
        kind = str(entry.output["kind"])
        if kind not in allowed:
            continue
        if not _matches_text(query=query, match_mode=match_mode, candidates=entry.candidates):
            continue
        total += 1
        kind_counts[kind] += 1
        if len(matching) < limit:
            matching.append(entry.output)

    return stabilize_json(
        {
            "project_status": _project_status(bundle),
            "design_unit_query": design_unit,
            "found_design_unit": True,
            "ambiguous_design_unit": False,
            "design_unit_candidates": [],
            "query": query,
            "match_mode": match_mode,
            "summary": {
                "total": total,
                "by_kind": dict(sorted(kind_counts.items())),
                "truncation": _truncation(returned=len(matching), total=total),
            },
            "members": matching,
        }
    )
```

- [x] **Step 6: Wire server tool**

In `server.py`, import `find_member_core`, add `FindMemberResult`, add `PUBLIC_TOOL_NAMES["find_member"]`, add boolean args and max arg:

```python
MemberQueryArg = Annotated[
    str,
    Field(description="Member name or path to match inside `design_unit`."),
]
MaxMemberResultsArg = Annotated[
    int,
    Field(
        default=100,
        description="Maximum member hits to return before truncation.",
        json_schema_extra={"minimum": 0, "maximum": MAX_MEMBER_RESULTS},
    ),
]
```

Register:

```python
    @mcp.tool(
        name=PUBLIC_TOOL_NAMES["find_member"],
        annotations=READ_ONLY_ANNOTATIONS,
        description=(
            "Find ports, variables/nets, parameters, and child instances inside one design unit. "
            "Use this when `find_symbol` is too broad and the query is for a local net "
            "or instance name."
        ),
    )
    def find_member(
        project_root: ProjectRootArg,
        design_unit: DesignUnitNameArg,
        query: MemberQueryArg,
        files: OptionalFilesArg = None,
        filelist: OptionalFilelistArg = None,
        include_dirs: IncludeDirsArg = None,
        defines: DefinesArg = None,
        top_modules: TopModulesArg = None,
        match_mode: MatchModeArg = "exact",
        include_ports: bool = True,
        include_nets: bool = True,
        include_variables: bool = True,
        include_instances: bool = True,
        include_parameters: bool = True,
        max_results: MaxMemberResultsArg = 100,
    ) -> Annotated[CallToolResult, FindMemberResult | ToolErrorResult]:
        return run_project_tool(
            FindMemberResult,
            tool_name="find_member",
            tool_args={
                "design_unit": design_unit,
                "query": query,
                "match_mode": match_mode,
                "include_ports": include_ports,
                "include_nets": include_nets,
                "include_variables": include_variables,
                "include_instances": include_instances,
                "include_parameters": include_parameters,
                "max_results": max_results,
            },
            project_factory=lambda: resolve_project(
                project_root=project_root,
                files=files,
                filelist=filelist,
                include_dirs=include_dirs,
                defines=defines,
                top_modules=top_modules,
            ),
            callback=lambda bundle: find_member_core(
                bundle,
                design_unit=design_unit,
                query=query,
                match_mode=validate_match_mode(match_mode),
                include_ports=include_ports,
                include_nets=include_nets,
                include_variables=include_variables,
                include_instances=include_instances,
                include_parameters=include_parameters,
                max_results=bounded_int(
                    "max_results",
                    max_results,
                    minimum=0,
                    maximum=MAX_MEMBER_RESULTS,
                ),
            ),
        )
```

- [x] **Step 7: Add tests**

In `tests/test_analysis.py`, import `find_member` and append:

```python
def test_find_member_generated_nets() -> None:
    project = load_project_from_filelist(
        project_root=FIXTURES / "verilog_debug",
        filelist="project.f",
        top_modules=["debug_top"],
    )
    bundle = build_analysis(project)

    response_valid = find_member(
        bundle,
        design_unit="debug_stage",
        query="response__vld",
        match_mode="exact",
    )
    assert response_valid["found_design_unit"] is True
    assert response_valid["summary"]["total"] >= 1
    assert response_valid["members"][0]["name"] == "response__vld"
    assert response_valid["members"][0]["kind"] in {"port", "variable"}
    assert response_valid["members"][0]["location"]["path"] == "verilog_debug.sv"

    local_ready = find_member(
        bundle,
        design_unit="debug_stage",
        query="response_pop_fifo__rdy",
        match_mode="exact",
        include_ports=False,
    )
    assert local_ready["summary"]["total"] == 1
    assert local_ready["members"][0]["kind"] == "variable"

    child_instance = find_member(
        bundle,
        design_unit="debug_stage",
        query="u_sink",
        match_mode="exact",
        include_ports=False,
        include_variables=False,
    )
    assert child_instance["summary"]["total"] == 1
    assert child_instance["members"][0]["kind"] == "instance"
```

In `tests/test_server.py`, append:

```python
def test_find_member_tool() -> None:
    payload, is_error = _call_tool_json(
        PUBLIC_TOOL_NAMES["find_member"],
        {
            "project_root": str(FIXTURES / "verilog_debug"),
            "filelist": "project.f",
            "top_modules": ["debug_top"],
            "design_unit": "debug_stage",
            "query": "response_pop_fifo__rdy",
            "match_mode": "exact",
            "max_results": 5,
        },
    )

    assert not is_error
    assert payload["found_design_unit"] is True
    assert payload["summary"]["total"] == 1
    assert payload["members"][0]["name"] == "response_pop_fifo__rdy"
```

- [x] **Step 8: Run focused tests**

Run:

```bash
./.venv/bin/pytest -q tests/test_analysis.py::test_find_member_generated_nets tests/test_server.py::test_find_member_tool
```

Expected: both tests pass.

- [x] **Step 9: Commit member lookup**

```bash
git add src/pyslang_mcp/analysis.py src/pyslang_mcp/schemas.py src/pyslang_mcp/server.py tests/test_analysis.py tests/test_server.py
git commit -m "feat: add design-unit member lookup"
```

---

### Task 6: Normalize Instance Port Connections And Implement `pyslang_get_instance_connections`

**Files:**
- Modify: `src/pyslang_mcp/analysis.py`
- Modify: `src/pyslang_mcp/schemas.py`
- Modify: `src/pyslang_mcp/server.py`
- Modify: `tests/test_analysis.py`
- Modify: `tests/test_server.py`

**ASIC Evidence:**
- Lane: RTL
- Before evidence: `./.venv/bin/pytest -q tests/test_analysis.py::test_analysis_over_filelist_fixture`
- After evidence: `./.venv/bin/pytest -q tests/test_analysis.py::test_get_instance_connections_generated_fixture tests/test_server.py::test_get_instance_connections_tool`
- Supported claim: Focused instance port bindings are available with direction, expression snippet, and resolved actual symbol when pyslang exposes it.
- Unsupported claim: A port-connection dump proves end-to-end connectivity or driver validity.

- [x] **Step 1: Add connection schemas**

Add to `schemas.py` after `HierarchyPortConnection`:

```python
class InstanceConnectionRecord(StrictModel):
    port: str
    direction: str | None = None
    expression_kind: str
    expression_snippet: str | None = None
    connected_symbol: SymbolDeclaration | None = None
    source_location: Location | None = None


class GetInstanceConnectionsSummary(StrictModel):
    total: int
    truncation: TruncationInfo


class GetInstanceConnectionsResult(StrictModel):
    project_status: ProjectStatus
    query: str
    found: bool
    ambiguous: bool
    candidates: list[HierarchyNode]
    instance: HierarchyNode | None = None
    summary: GetInstanceConnectionsSummary
    connections: list[InstanceConnectionRecord]
```

- [x] **Step 2: Add expression unwrapping helper for port actuals**

Add to `analysis.py`:

```python
def _connection_actual_expression(connection: Any) -> Any:
    expression = connection.expression
    direction = getattr(getattr(connection.port, "direction", None), "name", None)
    if type(expression).__name__ == "AssignmentExpression" and direction in {"Out", "In" + "Out"}:
        return expression.left
    return expression


def _symbol_declaration_from_hit(hit: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": hit.get("name"),
        "kind": hit.get("kind", "Unknown"),
        "hierarchical_path": hit.get("hierarchical_path", ""),
        "lexical_path": hit.get("lexical_path", ""),
        "location": hit.get("location"),
    }
```

- [x] **Step 3: Add connection serializer**

Add:

```python
def _serialize_instance_connection(
    bundle: AnalysisBundle,
    instance: Any,
    connection: Any,
) -> IndexedInstanceConnection:
    actual = _connection_actual_expression(connection)
    symbol_hits = _expression_symbol_hits(actual)
    connected_symbol = None
    if symbol_hits:
        first = dict(symbol_hits[0])
        first["location"] = _serialize_location(
            bundle,
            getattr(getattr(actual, "symbol", None), "location", None),
        )
        connected_symbol = _symbol_declaration_from_hit(first)
    output = {
        "port": connection.port.name,
        "direction": _direction_name(connection.port),
        "expression_kind": connection.expression.kind.name,
        "expression_snippet": _source_snippet(bundle, connection.expression.sourceRange),
        "connected_symbol": connected_symbol,
        "source_location": _serialize_range_location(bundle, connection.expression.sourceRange),
    }
    return IndexedInstanceConnection(
        instance_path=str(instance.hierarchicalPath),
        port_name=connection.port.name,
        candidates=_candidate_tuple(
            (
                connection.port.name,
                str(instance.hierarchicalPath),
                getattr(instance, "name", None),
                output.get("expression_snippet"),
                connected_symbol.get("name") if connected_symbol else None,
                connected_symbol.get("hierarchical_path") if connected_symbol else None,
            )
        ),
        output=output,
    )
```

- [x] **Step 4: Populate connection index**

In `_build_index`, add:

```python
    connections_by_instance_path: defaultdict[str, list[IndexedInstanceConnection]] = defaultdict(list)
```

Inside the `Instance` block in `visit(symbol)`:

```python
            for connection in getattr(symbol, "portConnections", []):
                connections_by_instance_path[path].append(
                    _serialize_instance_connection(bundle, symbol, connection)
                )
```

In the `AnalysisIndex` return:

```python
        connections_by_instance_path={
            key: tuple(values) for key, values in connections_by_instance_path.items()
        },
```

- [x] **Step 5: Add core function**

Add after `get_hierarchy`:

```python
def get_instance_connections(
    bundle: AnalysisBundle,
    *,
    instance_path_or_name: str,
    max_connections: int = 200,
) -> dict[str, Any]:
    """Return focused port connections for one elaborated instance."""

    index = _analysis_index(bundle)
    exact_paths = [
        path
        for path in index.instance_records_by_path
        if path == instance_path_or_name
        or path.endswith(f".{instance_path_or_name}")
        or index.instance_records_by_path[path]["name"] == instance_path_or_name
    ]
    exact_paths = sorted(set(exact_paths))
    if len(exact_paths) != 1:
        candidates = [
            index.instance_records_by_path[path]
            for path in sorted(index.instance_records_by_path)
            if _matches_text(
                query=instance_path_or_name,
                match_mode="contains",
                candidates={
                    path,
                    index.instance_records_by_path[path]["name"],
                    index.instance_records_by_path[path].get("definition"),
                },
            )
        ][:10]
        return stabilize_json(
            {
                "project_status": _project_status(bundle),
                "query": instance_path_or_name,
                "found": False,
                "ambiguous": len(exact_paths) > 1,
                "candidates": [index.instance_records_by_path[path] for path in exact_paths] or candidates,
                "instance": None,
                "summary": {
                    "total": 0,
                    "truncation": _truncation(returned=0, total=0),
                },
                "connections": [],
            }
        )

    instance_path = exact_paths[0]
    entries = index.connections_by_instance_path.get(instance_path, ())
    limited_entries, truncation = limit_list(
        [entry.output for entry in entries],
        max_items=max_connections,
    )
    return stabilize_json(
        {
            "project_status": _project_status(bundle),
            "query": instance_path_or_name,
            "found": True,
            "ambiguous": False,
            "candidates": [],
            "instance": index.instance_records_by_path[instance_path],
            "summary": {
                "total": len(entries),
                "truncation": truncation,
            },
            "connections": limited_entries,
        }
    )
```

- [x] **Step 6: Wire server tool**

Add `GetInstanceConnectionsResult`, `get_instance_connections_core`, and `PUBLIC_TOOL_NAMES["get_instance_connections"]`.

Add args:

```python
InstancePathArg = Annotated[
    str,
    Field(
        description=(
            "Exact elaborated instance path such as `top.u_child`, or an unambiguous instance "
            "name such as `u_child`."
        )
    ),
]
MaxConnectionsArg = Annotated[
    int,
    Field(
        default=200,
        description="Maximum port connections to return before truncation.",
        json_schema_extra={"minimum": 0, "maximum": MAX_CONNECTION_RESULTS},
    ),
]
```

Register:

```python
    @mcp.tool(
        name=PUBLIC_TOOL_NAMES["get_instance_connections"],
        annotations=READ_ONLY_ANNOTATIONS,
        description=(
            "Return a focused port-connection dump for one elaborated instance without expanding "
            "the full hierarchy tree."
        ),
    )
    def get_instance_connections(
        project_root: ProjectRootArg,
        instance_path_or_name: InstancePathArg,
        files: OptionalFilesArg = None,
        filelist: OptionalFilelistArg = None,
        include_dirs: IncludeDirsArg = None,
        defines: DefinesArg = None,
        top_modules: TopModulesArg = None,
        max_connections: MaxConnectionsArg = 200,
    ) -> Annotated[CallToolResult, GetInstanceConnectionsResult | ToolErrorResult]:
        return run_project_tool(
            GetInstanceConnectionsResult,
            tool_name="get_instance_connections",
            tool_args={
                "instance_path_or_name": instance_path_or_name,
                "max_connections": max_connections,
            },
            project_factory=lambda: resolve_project(
                project_root=project_root,
                files=files,
                filelist=filelist,
                include_dirs=include_dirs,
                defines=defines,
                top_modules=top_modules,
            ),
            callback=lambda bundle: get_instance_connections_core(
                bundle,
                instance_path_or_name=instance_path_or_name,
                max_connections=bounded_int(
                    "max_connections",
                    max_connections,
                    minimum=0,
                    maximum=MAX_CONNECTION_RESULTS,
                ),
            ),
        )
```

- [x] **Step 7: Add tests**

In `tests/test_analysis.py`, import `get_instance_connections` and append:

```python
def test_get_instance_connections_generated_fixture() -> None:
    project = load_project_from_filelist(
        project_root=FIXTURES / "verilog_debug",
        filelist="project.f",
        top_modules=["debug_top"],
    )
    bundle = build_analysis(project)

    connections = get_instance_connections(
        bundle,
        instance_path_or_name="debug_top.u_stage",
    )

    assert connections["found"] is True
    by_port = {connection["port"]: connection for connection in connections["connections"]}
    assert by_port["ctrl_out__rdy"]["direction"] == "In"
    assert by_port["ctrl_out__rdy"]["connected_symbol"]["name"] == "ctrl_out__rdy"
    assert by_port["response__vld"]["direction"] == "Out"
    assert by_port["response__vld"]["connected_symbol"]["name"] == "response__vld"
```

In `tests/test_server.py`, append:

```python
def test_get_instance_connections_tool() -> None:
    payload, is_error = _call_tool_json(
        PUBLIC_TOOL_NAMES["get_instance_connections"],
        {
            "project_root": str(FIXTURES / "verilog_debug"),
            "filelist": "project.f",
            "top_modules": ["debug_top"],
            "instance_path_or_name": "debug_top.u_stage",
            "max_connections": 10,
        },
    )

    assert not is_error
    assert payload["found"] is True
    assert payload["summary"]["total"] == 6
```

- [x] **Step 8: Run focused tests**

Run:

```bash
./.venv/bin/pytest -q tests/test_analysis.py::test_get_instance_connections_generated_fixture tests/test_server.py::test_get_instance_connections_tool
```

Expected: both tests pass.

- [x] **Step 9: Commit instance connections**

```bash
git add src/pyslang_mcp/analysis.py src/pyslang_mcp/schemas.py src/pyslang_mcp/server.py tests/test_analysis.py tests/test_server.py
git commit -m "feat: add focused instance connections"
```

---

### Task 7: Build Assignment Index And Implement `pyslang_get_assignments`

**Files:**
- Modify: `src/pyslang_mcp/analysis.py`
- Modify: `src/pyslang_mcp/schemas.py`
- Modify: `src/pyslang_mcp/server.py`
- Modify: `tests/test_analysis.py`
- Modify: `tests/test_server.py`

**ASIC Evidence:**
- Lane: RTL
- Before evidence: `./.venv/bin/pytest -q tests/test_analysis.py::test_verilog_debug_fixture_baseline`
- After evidence: `./.venv/bin/pytest -q tests/test_analysis.py::test_get_assignments_generated_fixture tests/test_server.py::test_get_assignments_tool`
- Supported claim: The tool reports continuous and procedural assignment expressions involving a named signal when pyslang exposes semantic expression bindings.
- Unsupported claim: The tool proves complete assignment coverage, absence of latches, or reset/timing correctness.

- [x] **Step 1: Add assignment schemas**

Add to `schemas.py`:

```python
class AssignmentSymbolRef(StrictModel):
    name: str | None = None
    kind: str
    hierarchical_path: str
    lexical_path: str


class AssignmentRecord(StrictModel):
    design_unit: str
    assignment_kind: Literal["continuous", "procedural"]
    location: Location | None = None
    lhs_snippet: str | None = None
    rhs_snippet: str | None = None
    expression_snippet: str | None = None
    lhs_symbols: list[AssignmentSymbolRef]
    rhs_symbols: list[AssignmentSymbolRef]
    enclosing_constructs: list[str]
    is_partial_or_select: bool
    evidence_source: Literal["semantic"]


class GetAssignmentsSummary(StrictModel):
    total: int
    by_assignment_kind: dict[str, int]
    truncation: TruncationInfo


class GetAssignmentsResult(StrictModel):
    project_status: ProjectStatus
    design_unit_query: str
    found_design_unit: bool
    ambiguous_design_unit: bool
    design_unit_candidates: list[DesignUnitRecord]
    signal: str
    role: Literal["lhs", "rhs", "both"]
    summary: GetAssignmentsSummary
    assignments: list[AssignmentRecord]
```

- [x] **Step 2: Add assignment context helper**

Add to `analysis.py`:

```python
def _enclosing_syntax_kinds(syntax: Any) -> list[str]:
    kinds: list[str] = []
    parent = getattr(syntax, "parent", None)
    while parent is not None and len(kinds) < 8:
        kind = getattr(getattr(parent, "kind", None), "name", None)
        if kind in {
            "ConditionalStatement",
            "ForLoopStatement",
            "CaseStatement",
            "AlwaysConstruct",
            "AlwaysFFBlock",
            "AlwaysCombBlock",
            "ContinuousAssign",
        }:
            kinds.append(kind)
        parent = getattr(parent, "parent", None)
    return kinds


def _assignment_kind_from_context(owner: Any, expression: Any) -> str | None:
    owner_kind = _symbol_kind_name(owner)
    if owner_kind == "ContinuousAssign":
        return "continuous"
    constructs = _enclosing_syntax_kinds(getattr(expression, "syntax", None))
    if any(kind.startswith("Always") for kind in constructs):
        return "procedural"
    return None


def _is_partial_or_select_lhs(expression: Any) -> bool:
    kind = getattr(getattr(expression, "kind", None), "name", "")
    return kind not in {"NamedValue"}
```

- [x] **Step 3: Add assignment serializer**

Add:

```python
def _make_assignment_entry(
    bundle: AnalysisBundle,
    *,
    design_unit: str,
    assignment_kind: str,
    expression: Any,
) -> IndexedAssignment | None:
    if type(expression).__name__ != "AssignmentExpression":
        return None
    lhs_symbols = [dict(hit) for hit in _expression_symbol_hits(expression.left)]
    rhs_symbols = [dict(hit) for hit in _expression_symbol_hits(expression.right)]
    if not lhs_symbols and not rhs_symbols:
        return None
    output = {
        "design_unit": design_unit,
        "assignment_kind": assignment_kind,
        "location": _serialize_range_location(bundle, expression.sourceRange),
        "lhs_snippet": _source_snippet(bundle, expression.left.sourceRange),
        "rhs_snippet": _source_snippet(bundle, expression.right.sourceRange),
        "expression_snippet": _source_snippet(bundle, expression.sourceRange),
        "lhs_symbols": lhs_symbols,
        "rhs_symbols": rhs_symbols,
        "enclosing_constructs": _enclosing_syntax_kinds(expression.syntax),
        "is_partial_or_select": _is_partial_or_select_lhs(expression.left),
        "evidence_source": "semantic",
    }
    lhs_candidates: list[str] = []
    rhs_candidates: list[str] = []
    for hit in lhs_symbols:
        lhs_candidates.extend(_symbol_hit_candidates(hit))
    for hit in rhs_symbols:
        rhs_candidates.extend(_symbol_hit_candidates(hit))
    return IndexedAssignment(
        design_unit=design_unit,
        lhs_candidates=_candidate_tuple(lhs_candidates),
        rhs_candidates=_candidate_tuple(rhs_candidates),
        output=output,
    )
```

- [x] **Step 4: Collect assignment entries in `_build_index`**

Add containers:

```python
    assignments_by_design_unit: defaultdict[str, list[IndexedAssignment]] = defaultdict(list)
    seen_assignments: set[tuple[str, str | None, str | None]] = set()
```

Inside `visit(symbol)`, add:

```python
        assignment_expression = getattr(symbol, "assignment", None)
        if assignment_expression is None and type(symbol).__name__ == "AssignmentExpression":
            assignment_expression = symbol
        assignment_kind = _assignment_kind_from_context(symbol, assignment_expression)
        design_unit = _symbol_design_unit(symbol)
        if assignment_expression is not None and assignment_kind is not None and design_unit:
            assignment_entry = _make_assignment_entry(
                bundle,
                design_unit=design_unit,
                assignment_kind=assignment_kind,
                expression=assignment_expression,
            )
            if assignment_entry is not None:
                location = assignment_entry.output.get("location")
                key = (
                    design_unit,
                    assignment_entry.output.get("expression_snippet"),
                    location.get("path") if isinstance(location, dict) else None,
                )
                if key not in seen_assignments:
                    seen_assignments.add(key)
                    assignments_by_design_unit[design_unit].append(assignment_entry)
```

In `AnalysisIndex` return:

```python
        assignments_by_design_unit={
            key: tuple(values) for key, values in assignments_by_design_unit.items()
        },
```

- [x] **Step 5: Add core function**

Add:

```python
AssignmentRole = Literal["lhs", "rhs", "both"]


def get_assignments(
    bundle: AnalysisBundle,
    *,
    design_unit: str,
    signal: str,
    role: AssignmentRole = "both",
    max_results: int = 100,
) -> dict[str, Any]:
    """Return assignments involving a signal in a design unit."""

    selected, candidates, ambiguous = _resolve_design_unit(bundle, name=design_unit)
    if selected is None:
        return stabilize_json(
            {
                "project_status": _project_status(bundle),
                "design_unit_query": design_unit,
                "found_design_unit": False,
                "ambiguous_design_unit": ambiguous,
                "design_unit_candidates": candidates,
                "signal": signal,
                "role": role,
                "summary": {
                    "total": 0,
                    "by_assignment_kind": {},
                    "truncation": _truncation(returned=0, total=0),
                },
                "assignments": [],
            }
        )

    entries = _analysis_index(bundle).assignments_by_design_unit.get(str(selected["name"]), ())
    outputs: list[dict[str, Any]] = []
    kind_counts: Counter[str] = Counter()
    total = 0
    limit = max(max_results, 0)
    for entry in entries:
        lhs_match = _matches_text(query=signal, match_mode="exact", candidates=entry.lhs_candidates)
        rhs_match = _matches_text(query=signal, match_mode="exact", candidates=entry.rhs_candidates)
        if role == "lhs" and not lhs_match:
            continue
        if role == "rhs" and not rhs_match:
            continue
        if role == "both" and not (lhs_match or rhs_match):
            continue
        total += 1
        kind_counts[str(entry.output["assignment_kind"])] += 1
        if len(outputs) < limit:
            outputs.append(entry.output)

    return stabilize_json(
        {
            "project_status": _project_status(bundle),
            "design_unit_query": design_unit,
            "found_design_unit": True,
            "ambiguous_design_unit": False,
            "design_unit_candidates": [],
            "signal": signal,
            "role": role,
            "summary": {
                "total": total,
                "by_assignment_kind": dict(sorted(kind_counts.items())),
                "truncation": _truncation(returned=len(outputs), total=total),
            },
            "assignments": outputs,
        }
    )
```

- [x] **Step 6: Wire server tool**

Add schema/core imports and public name.

Add role arg:

```python
AssignmentRoleArg = Annotated[
    str,
    Field(
        default="both",
        description="Signal role filter: `lhs`, `rhs`, or `both`.",
        json_schema_extra={"enum": ["lhs", "rhs", "both"]},
    ),
]
MaxAssignmentResultsArg = Annotated[
    int,
    Field(
        default=100,
        description="Maximum assignment hits to return before truncation.",
        json_schema_extra={"minimum": 0, "maximum": MAX_ASSIGNMENT_RESULTS},
    ),
]
```

Add validator:

```python
    def validate_assignment_role(role: str) -> AssignmentRole:
        valid_roles = {"lhs", "rhs", "both"}
        if role not in valid_roles:
            raise ToolInputError("`role` must be one of `lhs`, `rhs`, or `both`.")
        return cast(AssignmentRole, role)
```

Register:

```python
    @mcp.tool(
        name=PUBLIC_TOOL_NAMES["get_assignments"],
        annotations=READ_ONLY_ANNOTATIONS,
        description=(
            "Return continuous and procedural assignments involving a local signal in one design "
            "unit. Results include LHS/RHS snippets, referenced symbols, source location, and "
            "whether the LHS is structurally partial or select-based."
        ),
    )
    def get_assignments(
        project_root: ProjectRootArg,
        design_unit: DesignUnitNameArg,
        signal: SymbolQueryArg,
        files: OptionalFilesArg = None,
        filelist: OptionalFilelistArg = None,
        include_dirs: IncludeDirsArg = None,
        defines: DefinesArg = None,
        top_modules: TopModulesArg = None,
        role: AssignmentRoleArg = "both",
        max_results: MaxAssignmentResultsArg = 100,
    ) -> Annotated[CallToolResult, GetAssignmentsResult | ToolErrorResult]:
        return run_project_tool(
            GetAssignmentsResult,
            tool_name="get_assignments",
            tool_args={
                "design_unit": design_unit,
                "signal": signal,
                "role": role,
                "max_results": max_results,
            },
            project_factory=lambda: resolve_project(
                project_root=project_root,
                files=files,
                filelist=filelist,
                include_dirs=include_dirs,
                defines=defines,
                top_modules=top_modules,
            ),
            callback=lambda bundle: get_assignments_core(
                bundle,
                design_unit=design_unit,
                signal=signal,
                role=validate_assignment_role(role),
                max_results=bounded_int(
                    "max_results",
                    max_results,
                    minimum=0,
                    maximum=MAX_ASSIGNMENT_RESULTS,
                ),
            ),
        )
```

- [x] **Step 7: Add tests**

In `tests/test_analysis.py`, import `get_assignments` and append:

```python
def test_get_assignments_generated_fixture() -> None:
    project = load_project_from_filelist(
        project_root=FIXTURES / "verilog_debug",
        filelist="project.f",
        top_modules=["debug_top"],
    )
    bundle = build_analysis(project)

    drivers = get_assignments(
        bundle,
        design_unit="debug_stage",
        signal="response__vld",
        role="lhs",
    )
    assert drivers["found_design_unit"] is True
    assert drivers["summary"]["total"] == 1
    assert drivers["assignments"][0]["assignment_kind"] == "continuous"
    assert drivers["assignments"][0]["lhs_snippet"] == "response__vld"
    assert "stage_enable" in drivers["assignments"][0]["rhs_snippet"]

    loads = get_assignments(
        bundle,
        design_unit="debug_sink",
        signal="response__vld",
        role="rhs",
    )
    assert loads["summary"]["total"] >= 1
    assert set(loads["summary"]["by_assignment_kind"]) == {"continuous"}

    mixed_roles = get_assignments(
        bundle,
        design_unit="debug_sink",
        signal="sampled_data",
        role="both",
    )
    assert {"continuous", "procedural"} <= set(
        mixed_roles["summary"]["by_assignment_kind"]
    )
```

In `tests/test_server.py`, append:

```python
def test_get_assignments_tool() -> None:
    payload, is_error = _call_tool_json(
        PUBLIC_TOOL_NAMES["get_assignments"],
        {
            "project_root": str(FIXTURES / "verilog_debug"),
            "filelist": "project.f",
            "top_modules": ["debug_top"],
            "design_unit": "debug_stage",
            "signal": "response__vld",
            "role": "lhs",
            "max_results": 5,
        },
    )

    assert not is_error
    assert payload["summary"]["total"] == 1
    assert payload["assignments"][0]["lhs_snippet"] == "response__vld"
```

- [x] **Step 8: Run focused tests**

Run:

```bash
./.venv/bin/pytest -q tests/test_analysis.py::test_get_assignments_generated_fixture tests/test_server.py::test_get_assignments_tool
```

Expected: both tests pass.

- [x] **Step 9: Commit assignment extraction**

```bash
git add src/pyslang_mcp/analysis.py src/pyslang_mcp/schemas.py src/pyslang_mcp/server.py tests/test_analysis.py tests/test_server.py
git commit -m "feat: add assignment lookup"
```

---

### Task 8: Build Connectivity Graph And Implement `pyslang_trace_connectivity`

**Files:**
- Modify: `src/pyslang_mcp/analysis.py`
- Modify: `src/pyslang_mcp/schemas.py`
- Modify: `src/pyslang_mcp/server.py`
- Modify: `tests/test_analysis.py`
- Modify: `tests/test_server.py`

**ASIC Evidence:**
- Lane: RTL
- Before evidence: `./.venv/bin/pytest -q tests/test_analysis.py::test_get_assignments_generated_fixture tests/test_analysis.py::test_get_instance_connections_generated_fixture`
- After evidence: `./.venv/bin/pytest -q tests/test_analysis.py::test_trace_connectivity_generated_fixture tests/test_server.py::test_trace_connectivity_tool`
- Supported claim: The tool traces bounded structural connectivity through assignment edges and parent-child instance port bindings visible in the elaborated pyslang model.
- Unsupported claim: The tool proves complete fanin/fanout cones, CDC/RDC safety, timing paths, or multiple-driver correctness.

- [ ] **Step 1: Add trace schemas**

Add to `schemas.py`:

```python
class ConnectivityHop(StrictModel):
    source: str
    target: str
    kind: Literal["assignment", "port_binding"]
    instance_path: str | None = None
    design_unit: str | None = None
    port: str | None = None
    direction: str | None = None
    expression_snippet: str | None = None
    location: Location | None = None


class ConnectivityPath(StrictModel):
    start: str
    end: str
    hops: list[ConnectivityHop]
    stop_reason: str


class TraceConnectivitySummary(StrictModel):
    path_count: int
    edge_count_considered: int
    max_depth_requested: int
    truncation: TruncationInfo


class TraceConnectivityResult(StrictModel):
    project_status: ProjectStatus
    start: str
    direction: Literal["driver", "load", "both"]
    resolved_starts: list[str]
    summary: TraceConnectivitySummary
    paths: list[ConnectivityPath]
```

- [ ] **Step 2: Add edge helper**

Add:

```python
def _add_connectivity_edge(
    *,
    source: str,
    target: str,
    kind: str,
    output: dict[str, Any],
    edges_by_source: defaultdict[str, list[ConnectivityEdge]],
    edges_by_target: defaultdict[str, list[ConnectivityEdge]],
) -> None:
    if not source or not target or source == target:
        return
    edge = ConnectivityEdge(source=source, target=target, kind=kind, output=output)
    edges_by_source[source].append(edge)
    edges_by_target[target].append(edge)
```

- [ ] **Step 3: Add assignment edges**

In `_build_index`, add containers:

```python
    edges_by_source: defaultdict[str, list[ConnectivityEdge]] = defaultdict(list)
    edges_by_target: defaultdict[str, list[ConnectivityEdge]] = defaultdict(list)
```

After adding an `assignment_entry`, add:

```python
                    for rhs_hit in assignment_entry.output["rhs_symbols"]:
                        for lhs_hit in assignment_entry.output["lhs_symbols"]:
                            _add_connectivity_edge(
                                source=str(rhs_hit["hierarchical_path"]),
                                target=str(lhs_hit["hierarchical_path"]),
                                kind="assignment",
                                output={
                                    "source": str(rhs_hit["hierarchical_path"]),
                                    "target": str(lhs_hit["hierarchical_path"]),
                                    "kind": "assignment",
                                    "instance_path": None,
                                    "design_unit": design_unit,
                                    "port": None,
                                    "direction": None,
                                    "expression_snippet": assignment_entry.output.get("expression_snippet"),
                                    "location": assignment_entry.output.get("location"),
                                },
                                edges_by_source=edges_by_source,
                                edges_by_target=edges_by_target,
                            )
```

- [ ] **Step 4: Add port-binding edges**

Inside the instance `portConnections` loop, after serializing the connection:

```python
                formal = f"{path}.{connection.port.name}"
                connected = connection_entry.output.get("connected_symbol")
                actual = connected.get("hierarchical_path") if isinstance(connected, dict) else None
                direction = connection_entry.output.get("direction")
                if actual:
                    if direction == "In":
                        source, target = str(actual), formal
                    elif direction == "Out":
                        source, target = formal, str(actual)
                    else:
                        source, target = str(actual), formal
                    _add_connectivity_edge(
                        source=source,
                        target=target,
                        kind="port_binding",
                        output={
                            "source": source,
                            "target": target,
                            "kind": "port_binding",
                            "instance_path": path,
                            "design_unit": getattr(getattr(symbol, "definition", None), "name", None),
                            "port": connection.port.name,
                            "direction": direction,
                            "expression_snippet": connection_entry.output.get("expression_snippet"),
                            "location": connection_entry.output.get("source_location"),
                        },
                        edges_by_source=edges_by_source,
                        edges_by_target=edges_by_target,
                    )
                    if direction == "In" + "Out":
                        _add_connectivity_edge(
                            source=formal,
                            target=str(actual),
                            kind="port_binding",
                            output={
                                "source": formal,
                                "target": str(actual),
                                "kind": "port_binding",
                                "instance_path": path,
                                "design_unit": getattr(getattr(symbol, "definition", None), "name", None),
                                "port": connection.port.name,
                                "direction": direction,
                                "expression_snippet": connection_entry.output.get("expression_snippet"),
                                "location": connection_entry.output.get("source_location"),
                            },
                            edges_by_source=edges_by_source,
                            edges_by_target=edges_by_target,
                        )
```

In `AnalysisIndex` return:

```python
        connectivity_edges_by_source={
            key: tuple(values) for key, values in edges_by_source.items()
        },
        connectivity_edges_by_target={
            key: tuple(values) for key, values in edges_by_target.items()
        },
```

- [ ] **Step 5: Add start resolver and BFS**

Add:

```python
TraceDirection = Literal["driver", "load", "both"]


def _resolve_connectivity_starts(index: AnalysisIndex, start: str) -> list[str]:
    candidates: set[str] = set()
    all_nodes = set(index.connectivity_edges_by_source) | set(index.connectivity_edges_by_target)
    for node in all_nodes:
        if node == start or node.endswith(f".{start}"):
            candidates.add(node)
    return sorted(candidates)


def _trace_edges_for_direction(
    index: AnalysisIndex,
    node: str,
    direction: TraceDirection,
) -> tuple[ConnectivityEdge, ...]:
    if direction == "load":
        return index.connectivity_edges_by_source.get(node, ())
    if direction == "driver":
        return tuple(
            ConnectivityEdge(
                source=edge.target,
                target=edge.source,
                kind=edge.kind,
                output={**edge.output, "source": edge.target, "target": edge.source},
            )
            for edge in index.connectivity_edges_by_target.get(node, ())
        )
    return (
        *index.connectivity_edges_by_source.get(node, ()),
        *(
            ConnectivityEdge(
                source=edge.target,
                target=edge.source,
                kind=edge.kind,
                output={**edge.output, "source": edge.target, "target": edge.source},
            )
            for edge in index.connectivity_edges_by_target.get(node, ())
        ),
    )
```

- [ ] **Step 6: Add core trace function**

Add:

```python
def trace_connectivity(
    bundle: AnalysisBundle,
    *,
    start: str,
    direction: TraceDirection = "both",
    max_depth: int = 5,
    max_edges: int = 200,
) -> dict[str, Any]:
    """Trace bounded structural connectivity through assignments and port bindings."""

    index = _analysis_index(bundle)
    starts = _resolve_connectivity_starts(index, start)
    paths: list[dict[str, Any]] = []
    edge_count = 0
    queue: list[tuple[str, list[dict[str, Any]], set[str]]] = [
        (node, [], {node}) for node in starts
    ]
    while queue and len(paths) < max(max_edges, 0):
        node, hops, visited = queue.pop(0)
        if len(hops) >= max_depth:
            paths.append(
                {
                    "start": hops[0]["source"] if hops else node,
                    "end": node,
                    "hops": hops,
                    "stop_reason": "max_depth",
                }
            )
            continue
        next_edges = _trace_edges_for_direction(index, node, direction)
        if not next_edges:
            paths.append(
                {
                    "start": hops[0]["source"] if hops else node,
                    "end": node,
                    "hops": hops,
                    "stop_reason": "no_edges",
                }
            )
            continue
        for edge in next_edges:
            edge_count += 1
            if edge.target in visited:
                paths.append(
                    {
                        "start": hops[0]["source"] if hops else edge.source,
                        "end": edge.target,
                        "hops": [*hops, edge.output],
                        "stop_reason": "cycle",
                    }
                )
                continue
            queue.append((edge.target, [*hops, edge.output], {*visited, edge.target}))

    truncation = _truncation(returned=len(paths), total=max(len(paths), len(paths) + len(queue)))
    return stabilize_json(
        {
            "project_status": _project_status(bundle),
            "start": start,
            "direction": direction,
            "resolved_starts": starts,
            "summary": {
                "path_count": len(paths),
                "edge_count_considered": edge_count,
                "max_depth_requested": max_depth,
                "truncation": truncation,
            },
            "paths": paths,
        }
    )
```

- [ ] **Step 7: Wire server tool**

Add imports and public name.

Add args:

```python
TraceStartArg = Annotated[
    str,
    Field(description="Hierarchical signal path or unambiguous signal/instance.port suffix."),
]
TraceDirectionArg = Annotated[
    str,
    Field(
        default="both",
        description="Trace direction: `driver`, `load`, or `both`.",
        json_schema_extra={"enum": ["driver", "load", "both"]},
    ),
]
TraceDepthArg = Annotated[
    int,
    Field(
        default=5,
        description="Maximum connectivity hops to traverse.",
        json_schema_extra={"minimum": 1, "maximum": MAX_TRACE_DEPTH},
    ),
]
MaxTraceEdgesArg = Annotated[
    int,
    Field(
        default=200,
        description="Maximum trace paths to return before truncation.",
        json_schema_extra={"minimum": 0, "maximum": MAX_TRACE_EDGES},
    ),
]
```

Add validator:

```python
    def validate_trace_direction(direction: str) -> TraceDirection:
        valid_directions = {"driver", "load", "both"}
        if direction not in valid_directions:
            raise ToolInputError("`direction` must be one of `driver`, `load`, or `both`.")
        return cast(TraceDirection, direction)
```

Register:

```python
    @mcp.tool(
        name=PUBLIC_TOOL_NAMES["trace_connectivity"],
        annotations=READ_ONLY_ANNOTATIONS,
        description=(
            "Trace bounded structural connectivity through assignment edges and instance port "
            "bindings. This is frontend structural evidence only; it is not simulation, formal, "
            "CDC, timing, or multiple-driver signoff."
        ),
    )
    def trace_connectivity(
        project_root: ProjectRootArg,
        start: TraceStartArg,
        files: OptionalFilesArg = None,
        filelist: OptionalFilelistArg = None,
        include_dirs: IncludeDirsArg = None,
        defines: DefinesArg = None,
        top_modules: TopModulesArg = None,
        direction: TraceDirectionArg = "both",
        max_depth: TraceDepthArg = 5,
        max_edges: MaxTraceEdgesArg = 200,
    ) -> Annotated[CallToolResult, TraceConnectivityResult | ToolErrorResult]:
        return run_project_tool(
            TraceConnectivityResult,
            tool_name="trace_connectivity",
            tool_args={
                "start": start,
                "direction": direction,
                "max_depth": max_depth,
                "max_edges": max_edges,
            },
            project_factory=lambda: resolve_project(
                project_root=project_root,
                files=files,
                filelist=filelist,
                include_dirs=include_dirs,
                defines=defines,
                top_modules=top_modules,
            ),
            callback=lambda bundle: trace_connectivity_core(
                bundle,
                start=start,
                direction=validate_trace_direction(direction),
                max_depth=bounded_int(
                    "max_depth",
                    max_depth,
                    minimum=1,
                    maximum=MAX_TRACE_DEPTH,
                ),
                max_edges=bounded_int(
                    "max_edges",
                    max_edges,
                    minimum=0,
                    maximum=MAX_TRACE_EDGES,
                ),
            ),
        )
```

- [ ] **Step 8: Add tests**

In `tests/test_analysis.py`, import `trace_connectivity` and append:

```python
def test_trace_connectivity_generated_fixture() -> None:
    project = load_project_from_filelist(
        project_root=FIXTURES / "verilog_debug",
        filelist="project.f",
        top_modules=["debug_top"],
    )
    bundle = build_analysis(project)

    trace = trace_connectivity(
        bundle,
        start="debug_top.ctrl_out__rdy",
        direction="load",
        max_depth=5,
        max_edges=20,
    )

    assert "debug_top.ctrl_out__rdy" in trace["resolved_starts"]
    assert trace["summary"]["path_count"] >= 1
    flattened_targets = {
        hop["target"]
        for path in trace["paths"]
        for hop in path["hops"]
    }
    assert any(target.endswith("u_stage.ctrl_out__rdy") for target in flattened_targets)
```

In `tests/test_server.py`, append:

```python
def test_trace_connectivity_tool() -> None:
    payload, is_error = _call_tool_json(
        PUBLIC_TOOL_NAMES["trace_connectivity"],
        {
            "project_root": str(FIXTURES / "verilog_debug"),
            "filelist": "project.f",
            "top_modules": ["debug_top"],
            "start": "debug_top.ctrl_out__rdy",
            "direction": "load",
            "max_depth": 5,
            "max_edges": 20,
        },
    )

    assert not is_error
    assert "debug_top.ctrl_out__rdy" in payload["resolved_starts"]
    assert payload["summary"]["path_count"] >= 1
```

- [ ] **Step 9: Run focused tests**

Run:

```bash
./.venv/bin/pytest -q tests/test_analysis.py::test_trace_connectivity_generated_fixture tests/test_server.py::test_trace_connectivity_tool
```

Expected: both tests pass.

- [ ] **Step 10: Commit connectivity tracing**

```bash
git add src/pyslang_mcp/analysis.py src/pyslang_mcp/schemas.py src/pyslang_mcp/server.py tests/test_analysis.py tests/test_server.py
git commit -m "feat: trace structural connectivity"
```

---

### Task 9: Update MCP Tool Contract, Limit, Cache, And Stdio Smoke Tests

**Files:**
- Modify: `tests/test_server.py`
- Modify: `tests/test_mcp_stdio.py`

**ASIC Evidence:**
- Lane: RTL
- Before evidence: `./.venv/bin/pytest -q tests/test_server.py::test_tools_list_exposes_output_schema`
- After evidence: `./.venv/bin/pytest -q tests/test_server.py tests/test_mcp_stdio.py`
- Supported claim: MCP contracts expose output schemas, read-only annotations, hard bounds, structured errors, and cache reuse for new tools.
- Unsupported claim: Protocol smoke proves correctness on large proprietary designs.

- [ ] **Step 1: Update expected result models**

In both test files, add:

```python
        PUBLIC_TOOL_NAMES["find_member"]: "FindMemberResult",
        PUBLIC_TOOL_NAMES["get_assignments"]: "GetAssignmentsResult",
        PUBLIC_TOOL_NAMES["trace_connectivity"]: "TraceConnectivityResult",
        PUBLIC_TOOL_NAMES["get_instance_connections"]: "GetInstanceConnectionsResult",
        PUBLIC_TOOL_NAMES["summarize_diagnostics_by_code"]: "SummarizeDiagnosticsByCodeResult",
```

- [ ] **Step 2: Extend hard-limit schema assertions**

In `tests/test_server.py::test_tools_list_exposes_hard_limit_bounds`, add:

```python
        (PUBLIC_TOOL_NAMES["find_member"], "max_results", 0, MAX_MEMBER_RESULTS),
        (PUBLIC_TOOL_NAMES["get_assignments"], "max_results", 0, MAX_ASSIGNMENT_RESULTS),
        (
            PUBLIC_TOOL_NAMES["get_instance_connections"],
            "max_connections",
            0,
            MAX_CONNECTION_RESULTS,
        ),
        (PUBLIC_TOOL_NAMES["trace_connectivity"], "max_depth", 1, MAX_TRACE_DEPTH),
        (PUBLIC_TOOL_NAMES["trace_connectivity"], "max_edges", 0, MAX_TRACE_EDGES),
        (
            PUBLIC_TOOL_NAMES["summarize_diagnostics_by_code"],
            "max_groups",
            0,
            MAX_DIAGNOSTIC_GROUPS,
        ),
        (
            PUBLIC_TOOL_NAMES["summarize_diagnostics_by_code"],
            "max_examples_per_group",
            0,
            MAX_DIAGNOSTIC_EXAMPLES_PER_GROUP,
        ),
```

- [ ] **Step 3: Extend out-of-range tests**

In the parameter list for `test_limit_out_of_range_returns_structured_tool_error`, add entries for each new max arg, with required extra arguments:

```python
        (
            PUBLIC_TOOL_NAMES["find_member"],
            "max_results",
            MAX_MEMBER_RESULTS + 1,
            {"design_unit": "debug_stage", "query": "response__vld"},
        ),
        (
            PUBLIC_TOOL_NAMES["get_assignments"],
            "max_results",
            MAX_ASSIGNMENT_RESULTS + 1,
            {"design_unit": "debug_stage", "signal": "response__vld"},
        ),
        (
            PUBLIC_TOOL_NAMES["get_instance_connections"],
            "max_connections",
            MAX_CONNECTION_RESULTS + 1,
            {"instance_path_or_name": "debug_top.u_stage"},
        ),
        (
            PUBLIC_TOOL_NAMES["trace_connectivity"],
            "max_depth",
            MAX_TRACE_DEPTH + 1,
            {"start": "debug_top.ctrl_out__rdy"},
        ),
        (
            PUBLIC_TOOL_NAMES["trace_connectivity"],
            "max_edges",
            MAX_TRACE_EDGES + 1,
            {"start": "debug_top.ctrl_out__rdy"},
        ),
        (
            PUBLIC_TOOL_NAMES["summarize_diagnostics_by_code"],
            "max_groups",
            MAX_DIAGNOSTIC_GROUPS + 1,
            {},
        ),
        (
            PUBLIC_TOOL_NAMES["summarize_diagnostics_by_code"],
            "max_examples_per_group",
            MAX_DIAGNOSTIC_EXAMPLES_PER_GROUP + 1,
            {},
        ),
```

For these new entries, use `tests/fixtures/verilog_debug` as the fixture root in a small branch inside the test helper when the tool name is one of the Verilog analysis tools.

- [ ] **Step 4: Add invalid enum tests**

Append:

```python
def test_invalid_assignment_role_returns_structured_tool_error() -> None:
    payload, is_error = _call_tool_json(
        PUBLIC_TOOL_NAMES["get_assignments"],
        {
            "project_root": str(FIXTURES / "verilog_debug"),
            "filelist": "project.f",
            "top_modules": ["debug_top"],
            "design_unit": "debug_stage",
            "signal": "response__vld",
            "role": "driver",
        },
    )

    assert is_error
    assert payload["error"]["code"] == "invalid_arguments"
    assert "role" in payload["error"]["message"]


def test_invalid_trace_direction_returns_structured_tool_error() -> None:
    payload, is_error = _call_tool_json(
        PUBLIC_TOOL_NAMES["trace_connectivity"],
        {
            "project_root": str(FIXTURES / "verilog_debug"),
            "filelist": "project.f",
            "top_modules": ["debug_top"],
            "start": "debug_top.ctrl_out__rdy",
            "direction": "fanin",
        },
    )

    assert is_error
    assert payload["error"]["code"] == "invalid_arguments"
    assert "direction" in payload["error"]["message"]
```

- [ ] **Step 5: Add cache reuse test for a new tool**

Append:

```python
def test_identical_new_tool_calls_reuse_cached_tool_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    original_find_member = server_module.find_member_core

    def counted_find_member(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return cast(dict[str, Any], original_find_member(*args, **kwargs))

    monkeypatch.setattr(server_module, "find_member_core", counted_find_member)
    server = create_server(cache=AnalysisCache())
    arguments = {
        "project_root": str(FIXTURES / "verilog_debug"),
        "filelist": "project.f",
        "top_modules": ["debug_top"],
        "design_unit": "debug_stage",
        "query": "response__vld",
        "match_mode": "exact",
    }

    async def run() -> None:
        first = await server.call_tool(PUBLIC_TOOL_NAMES["find_member"], arguments)
        second = await server.call_tool(PUBLIC_TOOL_NAMES["find_member"], arguments)
        assert isinstance(first, CallToolResult)
        assert isinstance(second, CallToolResult)
        assert first.structuredContent == second.structuredContent

    asyncio.run(run())

    assert calls == 1
```

- [ ] **Step 6: Extend stdio tool calls**

In `tests/test_mcp_stdio.py::_assert_all_public_tools_call_successfully`, add calls for the five new tools. Use the generated-debug fixture for member, assignment, trace, and connection tools, and the broken fixture for diagnostic grouping.

- [ ] **Step 7: Run protocol tests**

Run:

```bash
./.venv/bin/pytest -q tests/test_server.py tests/test_mcp_stdio.py
```

Expected: all selected tests pass.

- [ ] **Step 8: Commit MCP contract coverage**

```bash
git add tests/test_server.py tests/test_mcp_stdio.py
git commit -m "test: cover new MCP tool contracts"
```

---

### Task 10: Update Public Documentation And Skill Guidance

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `docs/architecture.md`
- Modify: `skills/pyslang-verilog-context/SKILL.md`
- Modify: `skills/pyslang-verilog-context/evals/manifest.json`
- Create or modify one prompt under `skills/pyslang-verilog-context/evals/prompts/`

**ASIC Evidence:**
- Lane: RTL
- Before evidence: `./.venv/bin/pytest -q tests/test_mcp_stdio.py`
- After evidence:
  - `./.venv/bin/python skills/pyslang-verilog-context/scripts/validate_eval_fixtures.py`
  - `./.venv/bin/python skills/pyslang-verilog-context/scripts/run_comparison_evals.py`
- Supported claim: Public docs and skill prompts describe implemented tool behavior and limitations.
- Unsupported claim: Docs alone prove tool behavior without tests.

- [ ] **Step 1: Update README tool table**

Add rows:

```markdown
| Find a local member in one design unit | `pyslang_find_member` |
| Find assignments involving a signal | `pyslang_get_assignments` |
| Trace bounded structural connectivity | `pyslang_trace_connectivity` |
| Dump one instance's port connections | `pyslang_get_instance_connections` |
| Group diagnostics by code | `pyslang_summarize_diagnostics_by_code` |
```

- [ ] **Step 2: Add README usage examples**

Add a short section:

```markdown
Verilog debugging flow:

1. Use `pyslang_summarize_diagnostics_by_code` to separate repeated frontend warnings from unresolved dependency errors.
2. Use `pyslang_find_member` to locate local names such as `response__vld`.
3. Use `pyslang_get_assignments` to inspect visible continuous or procedural drivers and loads.
4. Use `pyslang_get_instance_connections` for one instance's port binding context.
5. Use `pyslang_trace_connectivity` for bounded structural paths through assignments and instance port bindings.

Connectivity tracing is structural frontend evidence. It is not simulation,
formal proof, CDC/RDC signoff, timing signoff, or a complete netlist-level
driver/load database.
```

- [ ] **Step 3: Update `AGENTS.md` public tool surface**

Add the five new tool names to the Product Scope list:

```markdown
- `pyslang_find_member`
- `pyslang_get_assignments`
- `pyslang_trace_connectivity`
- `pyslang_get_instance_connections`
- `pyslang_summarize_diagnostics_by_code`
```

- [ ] **Step 4: Update architecture docs**

In `docs/architecture.md`, update:

```markdown
server.py<br/>FastMCP instance<br/>15 @mcp.tool defs
```

and add the new core functions to the `analysis.py` node and extension-point text.

- [ ] **Step 5: Update skill workflow**

In `skills/pyslang-verilog-context/SKILL.md`, add:

```markdown
- Use `pyslang_summarize_diagnostics_by_code` before scanning long raw diagnostics in generated or large projects.
- Use `pyslang_find_member` when the question is local to one design unit and `pyslang_find_symbol` is too broad.
- Use `pyslang_get_assignments` for "what drives this signal" or "where is this signal used on RHS" questions.
- Use `pyslang_get_instance_connections` when one instance's port bindings are needed without a full hierarchy dump.
- Use `pyslang_trace_connectivity` for bounded structural tracing through assignments and instance port bindings.
```

Also add the limitation:

```markdown
`pyslang_trace_connectivity` is structural frontend evidence only. It does not
prove functional behavior, complete fanin/fanout, CDC/RDC safety, multiple-driver
cleanliness, synthesis quality, or timing closure.
```

- [ ] **Step 6: Add or update one deterministic eval case**

Add a manifest case using `fixtures/pyslang-mcp-tests` or a copied public-safe fixture. The expected evidence list should include at least:

```json
[
  "pyslang_parse_filelist",
  "pyslang_summarize_diagnostics_by_code",
  "pyslang_find_member",
  "pyslang_get_assignments",
  "pyslang_get_instance_connections",
  "pyslang_trace_connectivity"
]
```

The prompt should ask a realistic generated-net question and require the answer to state the structural-evidence limitation.

- [ ] **Step 7: Run docs and skill validation commands**

Run:

```bash
./.venv/bin/python skills/pyslang-verilog-context/scripts/validate_eval_fixtures.py
./.venv/bin/python skills/pyslang-verilog-context/scripts/run_comparison_evals.py
```

Expected: both commands complete successfully. If real LLM access is unavailable, document the exact failure and treat the skill changes as not fully validated.

- [ ] **Step 8: Commit documentation and skill updates**

```bash
git add README.md AGENTS.md docs/architecture.md skills/pyslang-verilog-context/SKILL.md skills/pyslang-verilog-context/evals
git commit -m "docs: document Verilog debug MCP tools"
```

---

### Task 11: Full Verification And Regression Sweep

**Files:**
- No source edits unless a verification failure requires a targeted fix.

**ASIC Evidence:**
- Lane: RTL
- Before evidence: all focused tests in Tasks 4 through 10.
- After evidence: full command list below.
- Supported claim: The repository's normal quality gates pass locally, and HDL/eval validation has been run or explicitly reported as unavailable.
- Unsupported claim: Passing these tests proves proprietary project behavior, timing closure, CDC/RDC closure, synthesis quality, or simulation correctness.

- [ ] **Step 1: Run formatting**

```bash
./.venv/bin/ruff format src tests scripts
```

Expected: command exits with status 0.

- [ ] **Step 2: Run lint**

```bash
./.venv/bin/ruff check src tests scripts
```

Expected: command exits with status 0.

- [ ] **Step 3: Run type checking**

```bash
./.venv/bin/pyright
```

Expected: command exits with status 0.

- [ ] **Step 4: Run full pytest suite**

```bash
./.venv/bin/pytest --cov=src/pyslang_mcp --cov-report=term-missing:skip-covered -q
```

Expected: tests pass with coverage report.

- [ ] **Step 5: Run security regression target**

```bash
./.venv/bin/pytest -q -m security
```

Expected: tests pass.

- [ ] **Step 6: Run MCP stdio protocol smoke**

```bash
./.venv/bin/pytest -q tests/test_mcp_stdio.py
```

Expected: tests pass and stderr contains no traceback.

- [ ] **Step 7: Run HDL example validation**

```bash
./.venv/bin/python scripts/validate_hdl_examples.py
```

Expected: command exits with status 0 when Verilator and local dependencies are available.

- [ ] **Step 8: Run full skill/eval validation required by `AGENTS.md`**

Run:

```bash
./.venv/bin/python skills/pyslang-verilog-context/scripts/validate_eval_fixtures.py
./.venv/bin/python skills/pyslang-verilog-context/scripts/run_comparison_evals.py
./.venv/bin/python scripts/run_mcp_comparison.py --output-dir reports/mcp_comparison_comprehensive_$(date +%Y%m%d)
./.venv/bin/python reports/real_examples_75/run_real75_comparison.py
./.venv/bin/python -m py_compile reports/real_examples_75/run_real75_comparison.py
```

Expected: commands complete successfully. If one cannot run because of unavailable local tooling, credentials, or runtime dependencies, record the exact command, error, and downgraded validation status in the PR notes.

- [ ] **Step 9: Inspect git diff**

```bash
git diff --stat
git diff -- src/pyslang_mcp tests README.md AGENTS.md docs/architecture.md skills/pyslang-verilog-context
```

Expected:

- No private paths, tokens, proprietary RTL, local workspace names, or unpublished planning notes.
- Public docs match implemented behavior.
- New fixture is small, synthetic, and public-safe.
- All new tools are read-only and bounded.

- [ ] **Step 10: Commit final verification fixes**

Only run this when verification required a small follow-up fix:

```bash
git add src tests README.md AGENTS.md docs/architecture.md skills/pyslang-verilog-context
git commit -m "test: complete Verilog debug tool validation"
```

---

## Self-Review Checklist

- Spec coverage: all requested tools except `pyslang_parse_generated_cache` are represented by tasks.
- Output bounds: every new list-like result has a max argument, schema bounds, runtime validation, and truncation metadata.
- Read-only invariant: no task adds file writes, simulation, synthesis, remote execution, or network fetch behavior to MCP tools.
- Cache invariant: all tools go through `run_project_tool` and `AnalysisCache.get_or_compute_tool_result`.
- Path invariant: all project inputs still go through `resolve_project`, `load_project_from_files`, or `load_project_from_filelist`.
- Hardware claim discipline: docs and tool descriptions label structural evidence limits.
- Eval trigger: changing `skills/pyslang-verilog-context/SKILL.md` and eval fixtures requires the full local eval validation listed in `AGENTS.md`.
