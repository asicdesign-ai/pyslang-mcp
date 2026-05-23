module naming_only_sync_trap (
  input  logic src_clk,
  input  logic dst_clk,
  input  logic src_d,
  output logic dst_q
);
  logic data_sync;

  always_ff @(posedge src_clk) begin
    data_sync <= src_d;
  end

  always_ff @(posedge dst_clk) begin
    dst_q <= data_sync;
  end
endmodule
