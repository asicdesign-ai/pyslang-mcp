module dual_clock_event_bridge (
    input  logic src_clk_i,
    input  logic src_rst_n,
    input  logic src_event_i,
    input  logic dst_clk_i,
    input  logic dst_rst_n,
    output logic dst_event_o
);
  logic src_toggle_q;
  logic dst_sample_q;

  always_ff @(posedge src_clk_i or negedge src_rst_n) begin
    if (!src_rst_n) begin
      src_toggle_q <= 1'b0;
    end else if (src_event_i) begin
      src_toggle_q <= ~src_toggle_q;
    end
  end

  always_ff @(posedge dst_clk_i or negedge dst_rst_n) begin
    if (!dst_rst_n) begin
      dst_sample_q <= 1'b0;
      dst_event_o  <= 1'b0;
    end else begin
      dst_event_o  <= src_toggle_q ^ dst_sample_q;
      dst_sample_q <= src_toggle_q;
    end
  end
endmodule
