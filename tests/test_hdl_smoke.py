# ruff: noqa: E402

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.hdl_examples import load_examples, validate_example

SMOKE_EXAMPLES = load_examples(smoke_only=True)


@pytest.mark.parametrize("example", SMOKE_EXAMPLES, ids=lambda example: str(example["id"]))
def test_hdl_smoke_examples(example: dict[str, object]) -> None:
    validate_example(example)
