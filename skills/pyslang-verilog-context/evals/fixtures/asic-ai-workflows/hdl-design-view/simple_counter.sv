module simple_counter (
  input  logic       clk,
  input  logic       rst_n,
  input  logic       enable,
  output logic [7:0] count
);
  logic [7:0] count_q;
  logic [7:0] count_d;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      count_q <= 8'h00;
    end else begin
      count_q <= count_d;
    end
  end

  assign count_d = enable ? (count_q + 8'h01) : count_q;
  assign count = count_q;
endmodule
