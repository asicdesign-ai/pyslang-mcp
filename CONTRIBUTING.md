# Contributing

`pyslang-mcp` is still alpha. Keep changes narrow, read-only, and technically honest.

## Development Setup

```bash
python -m venv .venv
./.venv/bin/pip install -e '.[dev]'
```

## Local Checks

```bash
ruff format src tests scripts
ruff check src tests scripts
pyright
pytest --cov=src/pyslang_mcp --cov-report=term-missing:skip-covered -q
```

## Full Eval Validation Before PRs

Every contributor must run the full local eval validation before opening a PR.
The CI eval job is intentionally a lean deterministic smoke subset and does not
require real LLM access.

Run the full local validation against all available Verilog examples and evals:

```bash
./.venv/bin/python scripts/validate_hdl_examples.py
./.venv/bin/python skills/pyslang-verilog-context/scripts/validate_eval_fixtures.py
./.venv/bin/python skills/pyslang-verilog-context/scripts/run_comparison_evals.py
./.venv/bin/python scripts/run_mcp_comparison.py --output-dir reports/mcp_comparison_comprehensive_$(date +%Y%m%d)
./.venv/bin/python reports/real_examples_75/run_real75_comparison.py
./.venv/bin/python -m py_compile reports/real_examples_75/run_real75_comparison.py
```

If you cannot run the full eval locally, say why in the PR and treat the change
as not fully validated.

## Repo Expectations

- Keep all MCP tools read-only.
- Do not allow path access outside the declared `project_root`.
- Prefer small analysis-core changes before MCP wrapper changes.
- Update `README.md` and `AGENTS.md` when implementation reality changes.
- Add or extend fixture-backed tests for behavior changes.
