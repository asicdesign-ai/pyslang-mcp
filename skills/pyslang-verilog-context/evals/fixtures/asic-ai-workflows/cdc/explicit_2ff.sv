module explicit_2ff (
  input  logic src_clk,
  input  logic dst_clk,
  input  logic src_d,
  output logic dst_q
);
  logic flag_a;
  logic flag_sync1;
  logic flag_sync2;

  always_ff @(posedge src_clk) begin
    flag_a <= src_d;
  end

  always_ff @(posedge dst_clk) begin
    flag_sync1 <= flag_a;
    flag_sync2 <= flag_sync1;
    dst_q <= flag_sync2;
  end
endmodule
