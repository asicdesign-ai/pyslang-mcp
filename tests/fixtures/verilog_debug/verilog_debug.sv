module debug_sink (
  input  logic clk,
  input  logic rst_n,
  input  logic sink_ready_i,
  input  logic response__vld,
  output logic response_pop_fifo__rdy,
  output logic [7:0] observed_data_o
);
  logic local_gate;
  logic [7:0] sampled_data;

  assign local_gate = rst_n & sink_ready_i;
  assign response_pop_fifo__rdy = local_gate & response__vld;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      sampled_data <= 8'h00;
    end else if (response__vld && response_pop_fifo__rdy) begin
      sampled_data <= 8'hA5;
    end
  end

  assign observed_data_o = sampled_data;
endmodule

module debug_stage (
  input  logic clk,
  input  logic rst_n,
  input  logic ctrl_out__rdy,
  output logic ctrl_iut__rdy,
  output logic response__vld,
  output logic [7:0] observed_data_o
);
  logic response_pop_fifo__rdy;
  logic stage_enable;

  assign stage_enable = ctrl_out__rdy & rst_n;
  assign response__vld = stage_enable;
  assign ctrl_iut__rdy = response_pop_fifo__rdy;

  debug_sink u_sink (
    .clk(clk),
    .rst_n(rst_n),
    .sink_ready_i(ctrl_out__rdy),
    .response__vld(response__vld),
    .response_pop_fifo__rdy(response_pop_fifo__rdy),
    .observed_data_o(observed_data_o)
  );
endmodule

module debug_top (
  input  logic clk,
  input  logic rst_n,
  input  logic downstream_ready_i,
  output logic upstream_ready_o,
  output logic response_valid_o,
  output logic [7:0] observed_data_o
);
  logic ctrl_out__rdy;
  logic ctrl_iut__rdy;
  logic response__vld;

  assign ctrl_out__rdy = downstream_ready_i;
  assign upstream_ready_o = ctrl_iut__rdy;
  assign response_valid_o = response__vld;

  debug_stage u_stage (
    .clk(clk),
    .rst_n(rst_n),
    .ctrl_out__rdy(ctrl_out__rdy),
    .ctrl_iut__rdy(ctrl_iut__rdy),
    .response__vld(response__vld),
    .observed_data_o(observed_data_o)
  );
endmodule
