module add8 (
  input  logic [7:0] lhs,
  input  logic [7:0] rhs,
  output logic [7:0] sum
);
  assign sum = lhs + rhs;
endmodule
