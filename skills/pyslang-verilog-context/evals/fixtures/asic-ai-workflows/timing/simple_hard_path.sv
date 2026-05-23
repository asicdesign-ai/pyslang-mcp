module simple_hard_path (
  input  logic       clk,
  input  logic [7:0] a,
  input  logic [7:0] b,
  output logic [7:0] y
);
  logic [7:0] sum_r;
  logic [7:0] out_r;

  always_ff @(posedge clk) begin
    sum_r <= a;
  end

  always_ff @(posedge clk) begin
    out_r <= sum_r + b;
  end

  assign y = out_r;
endmodule
