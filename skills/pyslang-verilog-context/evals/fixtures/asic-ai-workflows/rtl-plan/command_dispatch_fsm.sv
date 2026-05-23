module command_dispatch_fsm (
    input  logic clk_i,
    input  logic rst_n,
    input  logic cmd_valid_i,
    input  logic fault_i,
    input  logic clear_i,
    output logic busy_o,
    output logic error_o
);
  typedef enum logic [1:0] {
    IDLE_ST  = 2'd0,
    LOAD_ST  = 2'd1,
    EXEC_ST  = 2'd2,
    ERROR_ST = 2'd3
  } state_t;

  state_t state_q, state_d;

  always_comb begin
    state_d = state_q;
    unique case (state_q)
      IDLE_ST:  if (cmd_valid_i) state_d = LOAD_ST;
      LOAD_ST:  state_d = fault_i ? ERROR_ST : EXEC_ST;
      EXEC_ST:  if (fault_i) state_d = ERROR_ST;
      ERROR_ST: if (clear_i) state_d = IDLE_ST;
      default:  state_d = IDLE_ST;
    endcase
  end

  always_ff @(posedge clk_i or negedge rst_n) begin
    if (!rst_n) begin
      state_q <= IDLE_ST;
    end else begin
      state_q <= state_d;
    end
  end

  assign busy_o  = (state_q == LOAD_ST) || (state_q == EXEC_ST);
  assign error_o = (state_q == ERROR_ST);
endmodule
