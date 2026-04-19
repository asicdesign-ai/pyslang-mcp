## HDL Example Corpus

This directory contains a generated Verilog and SystemVerilog corpus for
`pyslang-mcp` development and validation.

The corpus is split into:

- `reference/`: clean examples that compile with both `pyslang` and Verilator
- `buggy/`: isolated duplicates with intentional functional bugs that still
  compile cleanly

The examples start with single-module designs and build up to small-IP projects
with filelists, include directories, packages, and multi-module composition.

### Difficulty Labels

Buggy variants are tagged in [corpus.json](/home/arik/projects/pyslang-mcp/examples/hdl/corpus.json)
with one of these difficulty levels:

- `easy`: obvious single-module behavioral bugs
- `medium`: bugs that require more control-flow or interface reasoning
- `hard`: bugs that hide in multi-module or race-sensitive behavior

### Validation Model

Every manifest entry is intended to pass:

- `pyslang` parsing and semantic analysis with zero diagnostics
- `verilator --lint-only`

The repository CI only runs a small smoke subset. Full corpus validation is
available locally:

```bash
./.venv/bin/python scripts/validate_hdl_examples.py
```

Run only the CI smoke subset locally:

```bash
./.venv/bin/python scripts/validate_hdl_examples.py --smoke-only
```

### Important Scope Note

Some buggy projects intentionally reuse the same module or package names as
their clean reference versions. Treat each example directory as an isolated
project root rather than loading the entire corpus as one compilation unit.
