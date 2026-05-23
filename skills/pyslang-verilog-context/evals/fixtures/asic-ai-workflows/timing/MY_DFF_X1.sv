module MY_DFF_X1 (
  output logic Q,
  input  logic D,
  input  logic CLK
);
  always_ff @(posedge CLK) begin
    Q <= D;
  end
endmodule
