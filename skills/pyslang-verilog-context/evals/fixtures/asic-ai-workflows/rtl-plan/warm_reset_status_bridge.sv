module warm_reset_status_bridge (
    input  logic clk_i,
    input  logic rst_n,
    input  logic cfg_rst_n,
    input  logic cfg_done_i,
    output logic status_ready_o
);
  logic cfg_done_q;

  always_ff @(posedge clk_i or negedge cfg_rst_n) begin
    if (!cfg_rst_n) begin
      cfg_done_q <= 1'b0;
    end else begin
      cfg_done_q <= cfg_done_i;
    end
  end

  always_ff @(posedge clk_i or negedge rst_n) begin
    if (!rst_n) begin
      status_ready_o <= 1'b0;
    end else begin
      status_ready_o <= cfg_done_q;
    end
  end
endmodule
