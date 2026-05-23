module multi_consumer_crossing (
  input  logic src_clk,
  input  logic dst_clk,
  input  logic src_d,
  output logic dst_q0,
  output logic dst_q1
);
  logic flag_a;

  always_ff @(posedge src_clk) begin
    flag_a <= src_d;
  end

  always_ff @(posedge dst_clk) begin
    dst_q0 <= flag_a;
  end

  always_ff @(posedge dst_clk) begin
    dst_q1 <= flag_a;
  end
endmodule
