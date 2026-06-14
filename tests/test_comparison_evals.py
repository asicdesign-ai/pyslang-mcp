from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def _load_comparison_module() -> ModuleType:
    script = (
        Path(__file__).resolve().parents[1]
        / "skills"
        / "pyslang-verilog-context"
        / "scripts"
        / "run_comparison_evals.py"
    )
    spec = importlib.util.spec_from_file_location("run_comparison_evals", script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_new_tool_summaries_use_public_schema_fields() -> None:
    module = _load_comparison_module()

    assignments = module.summarize_tool_payload(
        "pyslang_get_assignments",
        {
            "found_design_unit": True,
            "signal": "response__vld",
            "summary": {"total": 1, "by_assignment_kind": {"continuous": 1}},
        },
        False,
    )
    connections = module.summarize_tool_payload(
        "pyslang_get_instance_connections",
        {
            "found": True,
            "instance": {"hierarchical_path": "debug_top.u_stage"},
            "summary": {"total": 6},
        },
        False,
    )
    trace = module.summarize_tool_payload(
        "pyslang_trace_connectivity",
        {
            "resolved_starts": ["debug_top.ctrl_out__rdy"],
            "summary": {"path_count": 7, "edge_count_considered": 12},
        },
        False,
    )

    assert assignments["signal"] == "response__vld"
    assert assignments["by_assignment_kind"] == {"continuous": 1}
    assert connections["instance_path"] == "debug_top.u_stage"
    assert trace["edge_count"] == 12
