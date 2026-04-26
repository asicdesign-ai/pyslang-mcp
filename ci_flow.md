# CI Smoke Checks Summary

The current CI has a dedicated `hdl-smoke` job that validates a small HDL
example subset with both `pyslang-mcp` and Verilator.

```mermaid
flowchart TD
    A[Push to main or PR] --> B[CI workflow]

    B --> C[test matrix]
    C --> C1[Ubuntu Python 3.11]
    C --> C2[Ubuntu Python 3.12]
    C --> C3[macOS Python 3.12]
    C1 --> C4[ruff format check]
    C2 --> C4
    C3 --> C4
    C4 --> C5[ruff lint]
    C5 --> C6[pyright]
    C6 --> C7[pytest with coverage]

    B --> D[hdl-smoke job]
    D --> D1[Ubuntu latest]
    D1 --> D2[Set up Python 3.12]
    D2 --> D3[Install Verilator]
    D3 --> D4[pip install -e .[dev]]
    D4 --> D5[pytest -q tests/test_hdl_smoke.py]

    D5 --> E[Load corpus examples where ci_smoke=true]
    E --> F[For each smoke example]
    F --> G[pyslang-mcp load project]
    G --> H[build_analysis]
    H --> I[get_diagnostics must be zero]
    F --> J[Run verilator --lint-only]
    J --> K[Verilator must exit 0]
```

## What `hdl-smoke` Runs

The CI job runs:

```bash
pytest -q tests/test_hdl_smoke.py
```

That test loads HDL corpus entries from `examples/hdl/corpus.json` where:

```json
"ci_smoke": true
```

Current smoke examples:

| Example | Type | Project shape | Purpose |
|---|---:|---|---|
| `simple_counter_ref` | reference | single Verilog module | Basic Verilog parse/lint path |
| `edge_detect_ref` | reference | single SystemVerilog module | Basic SystemVerilog constructs |
| `sync_fifo_ref` | reference | multi-file filelist IP | Filelist, includes, package, multi-module flow |
| `apb_timer_irq_race_bug` | buggy corpus example | multi-file filelist IP | Ensures intentionally buggy examples are still syntactically/compiler clean |

## Per-Example Validation

For every smoke example, CI does two validations.

1. `pyslang-mcp` validation:
   - Loads the project from explicit files or `project.f`.
   - Applies top-module settings.
   - Builds the `pyslang` analysis bundle.
   - Calls `get_diagnostics`.
   - Fails if any parse or semantic diagnostics are reported.

2. Verilator validation:
   - Builds a command like:

   ```bash
   verilator --lint-only --top-module <top> -I<include_dir> <files...>
   ```

   - Adds include dirs and defines from the normalized project config.
   - Fails if Verilator exits non-zero.

## What It Does Not Currently Do

The CI smoke job does not validate the full 13-example HDL corpus. It only runs
the `ci_smoke=true` subset. The broader script
`scripts/validate_hdl_examples.py` can validate all examples locally, but it is
not currently wired into CI.
