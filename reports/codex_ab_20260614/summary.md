# Codex Verilog Context A/B Eval

Generated: 2026-06-14T07:19:43.983659+00:00
Model: `gpt-5.5` (`xhigh` reasoning)
Trials per case and arm: 3

| Arm | Correct trials | Accuracy | Consistent cases | Required-tool rate |
|---|---:|---:|---:|---:|
| no_skill_no_mcp | 39/60 | 65.0% | 16/20 | 0.0% |
| skill_mcp | 57/60 | 95.0% | 20/20 | 100.0% |

## Cases

### sync_child_path: Resolved child instance path

Expected: `sync_fifo.u_sync_fifo_mem`

- `no_skill_no_mcp`: 3/3 correct; answers=['sync_fifo.u_sync_fifo_mem', 'sync_fifo.u_sync_fifo_mem', 'sync_fifo.u_sync_fifo_mem']; consistent=True
- `skill_mcp`: 3/3 correct; answers=['sync_fifo.u_sync_fifo_mem', 'sync_fifo.u_sync_fifo_mem', 'sync_fifo.u_sync_fifo_mem']; consistent=True

### sync_child_definition: Child instance module definition

Expected: `sync_fifo_mem`

- `no_skill_no_mcp`: 3/3 correct; answers=['sync_fifo_mem', 'sync_fifo_mem', 'sync_fifo_mem']; consistent=True
- `skill_mcp`: 3/3 correct; answers=['sync_fifo_mem', 'sync_fifo_mem', 'sync_fifo_mem']; consistent=True

### sync_output_ports: sync_fifo output port count

Expected: `4`

- `no_skill_no_mcp`: 3/3 correct; answers=['4', '4', '4']; consistent=True
- `skill_mcp`: 3/3 correct; answers=['4', '4', '4']; consistent=True

### sync_tracked_paths: Normalized tracked path count

Expected: `6`

- `no_skill_no_mcp`: 3/3 correct; answers=['6', '6', '6']; consistent=True
- `skill_mcp`: 3/3 correct; answers=['6', '6', '6']; consistent=True

### sync_package_include: Package file that includes fifo_defs.svh

Expected: `sync_fifo_pkg.sv`

- `no_skill_no_mcp`: 0/3 correct; answers=['project/sync_fifo_pkg.sv', 'project/sync_fifo_pkg.sv', 'project/sync_fifo_pkg.sv']; consistent=True
- `skill_mcp`: 3/3 correct; answers=['sync_fifo_pkg.sv', 'sync_fifo_pkg.sv', 'sync_fifo_pkg.sv']; consistent=True

### push_fire_reference_kind: push_fire named reference classification

Expected: `named_value`

- `no_skill_no_mcp`: 0/3 correct; answers=['unknown', 'write', 'read']; consistent=False
- `skill_mcp`: 3/3 correct; answers=['named_value', 'named_value', 'named_value']; consistent=True

### timer_core_ports: timer_core total port count

Expected: `9`

- `no_skill_no_mcp`: 3/3 correct; answers=['9', '9', '9']; consistent=True
- `skill_mcp`: 3/3 correct; answers=['9', '9', '9']; consistent=True

### tick_hier_path: tick declaration hierarchical path

Expected: `apb_timer.u_timer_core.tick`

- `no_skill_no_mcp`: 3/3 correct; answers=['apb_timer.u_timer_core.tick', 'apb_timer.u_timer_core.tick', 'apb_timer.u_timer_core.tick']; consistent=True
- `skill_mcp`: 3/3 correct; answers=['apb_timer.u_timer_core.tick', 'apb_timer.u_timer_core.tick', 'apb_timer.u_timer_core.tick']; consistent=True

### prescale_q_count: prescale_q declaration count

Expected: `2`

- `no_skill_no_mcp`: 3/3 correct; answers=['2', '2', '2']; consistent=True
- `skill_mcp`: 3/3 correct; answers=['2', '2', '2']; consistent=True

### buggy_apb_diagnostics: Buggy APB parse and semantic diagnostic count

Expected: `0`

- `no_skill_no_mcp`: 0/3 correct; answers=['0 parse diagnostics and 0 semantic diagnostics', '0 parse diagnostics, 0 semantic diagnostics', 'unknown']; consistent=False
- `skill_mcp`: 3/3 correct; answers=['0', '0', '0']; consistent=True

### broken_project_status: Broken fixture project status

Expected: `incomplete`

- `no_skill_no_mcp`: 0/3 correct; answers=['unknown', 'unknown', 'unknown']; consistent=True
- `skill_mcp`: 3/3 correct; answers=['incomplete', 'incomplete', 'incomplete']; consistent=True

### data_t_reference_kind: data_t declared-type reference classification

Expected: `declared_type`

- `no_skill_no_mcp`: 1/3 correct; answers=['unknown', 'unknown', 'declared_type']; consistent=False
- `skill_mcp`: 3/3 correct; answers=['declared_type', 'declared_type', 'declared_type']; consistent=True

### multi_file_width_define: Effective WIDTH preprocessor define

Expected: `WIDTH=8`

- `no_skill_no_mcp`: 0/3 correct; answers=['8', '8', '8']; consistent=True
- `skill_mcp`: 0/3 correct; answers=['8', '8', '8']; consistent=True

### multi_file_child_path: multi_file top child instance path

Expected: `top.u_child`

- `no_skill_no_mcp`: 3/3 correct; answers=['top.u_child', 'top.u_child', 'top.u_child']; consistent=True
- `skill_mcp`: 3/3 correct; answers=['top.u_child', 'top.u_child', 'top.u_child']; consistent=True

### apb_design_unit_total: APB timer design-unit inventory

Expected: `3`

- `no_skill_no_mcp`: 3/3 correct; answers=['3', '3', '3']; consistent=True
- `skill_mcp`: 3/3 correct; answers=['3', '3', '3']; consistent=True

### sync_pkg_function_count: sync_fifo_pkg function count

Expected: `2`

- `no_skill_no_mcp`: 3/3 correct; answers=['2', '2', '2']; consistent=True
- `skill_mcp`: 3/3 correct; answers=['2', '2', '2']; consistent=True

### sync_mem_port_count: sync_fifo_mem port count

Expected: `6`

- `no_skill_no_mcp`: 3/3 correct; answers=['6', '6', '6']; consistent=True
- `skill_mcp`: 3/3 correct; answers=['6', '6', '6']; consistent=True

### timer_ctrl_type_reference_count: timer_ctrl_t bound reference count

Expected: `2`

- `no_skill_no_mcp`: 0/3 correct; answers=['1', '1', '1']; consistent=True
- `skill_mcp`: 3/3 correct; answers=['2', '2', '2']; consistent=True

### tap_delay_for_keyword_count: tap_delay_line for-loop syntax count

Expected: `3`

- `no_skill_no_mcp`: 3/3 correct; answers=['3', '3', '3']; consistent=True
- `skill_mcp`: 3/3 correct; answers=['3', '3', '3']; consistent=True

### apb_timer_include_path: APB timer package include path

Expected: `apb_timer_defs.svh`

- `no_skill_no_mcp`: 2/3 correct; answers=['include/apb_timer_defs.svh', 'apb_timer_defs.svh', 'apb_timer_defs.svh']; consistent=False
- `skill_mcp`: 3/3 correct; answers=['apb_timer_defs.svh', 'apb_timer_defs.svh', 'apb_timer_defs.svh']; consistent=True
