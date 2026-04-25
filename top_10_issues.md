# Top 10 Issues Before Publicizing `pyslang-mcp`

Review date: 2026-04-25

Reviewed commit: `8852d60` (`main`, after `git pull --ff-only`)

This review used the local `mcp-builder` skill as the quality lens: MCP tool
design, schema clarity, error handling, pagination and limits, safety,
packaging, testing, and evaluation readiness.

## Verification Run

The current repo is a credible local alpha. These checks passed locally after
refreshing the editable dev install:

```bash
./.venv/bin/ruff check src tests scripts
./.venv/bin/pyright
./.venv/bin/pytest --cov=src/pyslang_mcp --cov-report=term-missing:skip-covered -q
./.venv/bin/python scripts/validate_hdl_examples.py
./.venv/bin/python -m pip wheel . -w /tmp/pyslang-mcp-wheel --no-deps
```

Observed test result: `20 passed`, `89%` total coverage.

## 5. HTTP transport is exposed before the security model exists

The CLI exposes `--transport streamable-http` and starts a local HTTP server,
but the docs state hosted mode is design-only and should not be treated as just
exposing the local process over the network.

Evidence:

- CLI accepts `streamable-http`:
  [src/pyslang_mcp/__main__.py](src/pyslang_mcp/__main__.py)
- Hosted deployment docs explicitly require auth, authorization, and workspace
  isolation before remote use: [REMOTE_DEPLOYMENT.md](REMOTE_DEPLOYMENT.md)

Why it matters:

Even though FastMCP binds locally by default in current testing, advertising an
HTTP transport before auth, workspace identity, request limits, and audit
logging exist creates a risky product signal.

Recommended fix:

Hide or mark HTTP transport as experimental behind an explicit flag until the
workspace-scoped design exists. For any HTTP mode, add auth hooks, workspace
root mapping, rate limits, request size limits, timeout controls, and audit
logging.

## 6. Tool error handling is incomplete

The central `run_tool` wrapper catches invalid argument combinations and project
loader errors, but it does not catch validation errors from Pydantic, unexpected
`pyslang` exceptions, serialization failures, or schema-validation regressions.
Some invalid inputs can still surface as FastMCP `ToolError` exceptions instead
of the structured error payload promised by the docs.

Evidence:

- `run_tool` catches only `ToolInputError`, `PathOutsideRootError`, and
  `ProjectLoadError`: [src/pyslang_mcp/server.py](src/pyslang_mcp/server.py)
- Structured error schemas exist but are only used for those cases:
  [src/pyslang_mcp/schemas.py](src/pyslang_mcp/schemas.py)
- README promises structured recoverable tool errors:
  [README.md](README.md)

Why it matters:

Agents need actionable, predictable errors. Public clients should not see raw
validation traces or framework exceptions for common bad input.

Recommended fix:

Add a broader error translation layer. Convert Pydantic validation issues,
unsupported enum values, `pyslang` failures, Unicode/file-read failures, and
internal schema mismatches into structured MCP tool errors with stable codes and
hints. Keep internal details out of user-facing messages.

## 7. Release and public metadata are not ready

The package can build a wheel, but public release plumbing and metadata are not
complete. There is no publish workflow, no MCP Registry manifest or automation,
no `SECURITY.md`, no project URLs/authors in `pyproject.toml`, and README still
says there is no PyPI or registry release.

Evidence:

- README status lists release gaps: [README.md](README.md)
- Publishing plan still calls out PyPI and MCP Registry work:
  [pyslang-mcp-plan.md](pyslang-mcp-plan.md)
- Package metadata is minimal: [pyproject.toml](pyproject.toml)

Why it matters:

Publicizing an MCP should give users a clear install path, provenance, security
contact, changelog/release story, supported platforms, and registry identity.

Recommended fix:

Add project URLs, author/maintainer metadata, `SECURITY.md`, supported-platform
notes, trusted publishing to PyPI, release workflow, and MCP Registry metadata.
Then publish an explicit alpha release with known limitations.

## 8. The wheel includes a dev/test helper that is broken outside the repo

`pyslang_mcp.hdl_examples` is included in the package, but it assumes the
checked-in `examples/hdl` corpus exists two directories above the installed
module. The wheel does not include that corpus. In an extracted wheel,
`CORPUS_PATH` resolves to a nonexistent path.

Evidence:

- Repo-root assumption:
  [src/pyslang_mcp/hdl_examples.py](src/pyslang_mcp/hdl_examples.py)
- The helper is packaged through the whole `src/pyslang_mcp` package:
  [pyproject.toml](pyproject.toml)
- Validation script imports the packaged helper:
  [scripts/validate_hdl_examples.py](scripts/validate_hdl_examples.py)

Why it matters:

Packaged users should not receive broken repo-local test helpers in the runtime
package surface. This also confuses API boundaries for an alpha release.

Recommended fix:

Move HDL corpus helpers under `tests` or a non-packaged support module, or
package the corpus intentionally as package data and make the helper robust
when data is unavailable.

## 9. Tests and evaluations are not yet release gates

CI is useful, but it does not yet enforce coverage thresholds, wheel-install
smoke tests, stdio subprocess protocol tests, MCP Inspector checks, Windows
validation, performance budgets, or automated evaluation runs. The current
evaluation questions are also highly tool-explicit instead of realistic
agent-facing tasks.

Evidence:

- CI runs checks but has no coverage threshold or wheel-install job:
  [.github/workflows/ci.yml](.github/workflows/ci.yml)
- Evaluation file exists but is not wired into CI:
  [evaluation.xml](evaluation.xml)
- Current tests are fixture-backed but still small:
  [tests](tests)

Why it matters:

For a public MCP, users and client authors need confidence that the package
works when installed like a user installs it, that protocol behavior works over
stdio, and that tool schemas remain stable.

Recommended fix:

Add CI jobs for wheel build and install, CLI entrypoint smoke, stdio subprocess
tool calls, coverage threshold, JSON golden snapshots, evaluation harness, and
performance smoke tests. Add Windows only once `pyslang` wheel/platform support
is confirmed.

## 10. Schemas are structured but not versioned or frozen

The repo now has Pydantic output models and FastMCP output schemas, which is a
good foundation. But README still says long-term schemas are not frozen, and
the payloads do not carry schema versions.

Evidence:

- Structured schemas are defined in [src/pyslang_mcp/schemas.py](src/pyslang_mcp/schemas.py)
- README explicitly says schemas are still alpha:
  [README.md](README.md)
- MCP tool registration exposes output schemas:
  [src/pyslang_mcp/server.py](src/pyslang_mcp/server.py)

Why it matters:

Once users wire agents and workflows to this MCP, response-shape churn becomes
a real compatibility problem.

Recommended fix:

Add a schema/version field to every result or a shared envelope, define
compatibility policy, create golden-output snapshots, and decide which fields
are stable before the first public alpha announcement.
