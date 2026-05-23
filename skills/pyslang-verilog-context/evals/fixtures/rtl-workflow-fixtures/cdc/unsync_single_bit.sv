module unsync_single_bit (
  input  logic src_clk,
  input  logic dst_clk,
  input  logic src_d,
  output logic dst_q
);
  logic flag_a;

  always_ff @(posedge src_clk) begin
    flag_a <= src_d;
  end

  always_ff @(posedge dst_clk) begin
    dst_q <= flag_a;
  end
endmodule
