module unresolved_ff_like_macro (
  input  logic clk,
  input  logic d,
  output logic q
);
  MY_DFF_X1 u_reg (
    .Q(q),
    .D(d),
    .CLK(clk)
  );
endmodule
