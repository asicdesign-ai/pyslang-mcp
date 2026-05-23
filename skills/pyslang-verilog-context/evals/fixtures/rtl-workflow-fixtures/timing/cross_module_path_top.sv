module cross_module_path (
  input  logic       clk,
  input  logic [7:0] a,
  input  logic [7:0] b,
  output logic [7:0] y
);
  logic [7:0] a_r;
  logic [7:0] sum_w;
  logic [7:0] y_r;

  always_ff @(posedge clk) begin
    a_r <= a;
  end

  add8 u_add (
    .lhs(a_r),
    .rhs(b),
    .sum(sum_w)
  );

  always_ff @(posedge clk) begin
    y_r <= sum_w;
  end

  assign y = y_r;
endmodule
