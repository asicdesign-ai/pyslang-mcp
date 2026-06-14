Use `pyslang-mcp` if available to analyze the local SystemVerilog fixture.

First group any diagnostics, then inspect the `debug_stage` member and
assignment context, the `debug_top.u_stage` port bindings, and the bounded
connectivity path from `ctrl_out__rdy` to `response__vld`.

Answer only after compiler-backed evidence is available, and state that the
result is structural frontend evidence only. Do not present it as simulation,
formal proof, CDC/RDC signoff, timing signoff, or a complete fanin/fanout
database.
