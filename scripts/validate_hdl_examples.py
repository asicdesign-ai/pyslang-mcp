# ruff: noqa: E402

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.hdl_examples import (
    load_examples,
    validate_example,
    validate_manifest_file_coverage,
    validate_manifest_roots,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate generated HDL example projects with pyslang and Verilator."
    )
    parser.add_argument(
        "--smoke-only",
        action="store_true",
        help="Validate only the small CI smoke subset.",
    )
    args = parser.parse_args()

    examples = load_examples(smoke_only=args.smoke_only)
    validate_manifest_roots(load_examples())
    if not args.smoke_only:
        validate_manifest_file_coverage(load_examples())

    for example in examples:
        validate_example(example)
        kind = example["kind"]
        difficulty = example.get("difficulty", "reference")
        print(f"validated {example['id']} ({kind}, {difficulty})")

    print(f"validated {len(examples)} example projects")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
