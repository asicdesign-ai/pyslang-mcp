module single_clock_controller (
    input  logic       clk_i,
    input  logic       rst_n,
    input  logic       start_i,
    input  logic       stop_i,
    input  logic       tick_i,
    input  logic [7:0] threshold_i,
    output logic       busy_o,
    output logic       done_o
);
  logic [7:0] count_q;

  always_ff @(posedge clk_i or negedge rst_n) begin
    if (!rst_n) begin
      busy_o  <= 1'b0;
      done_o  <= 1'b0;
      count_q <= '0;
    end else begin
      done_o <= 1'b0;

      if (start_i) begin
        busy_o  <= 1'b1;
        count_q <= '0;
      end else if (stop_i) begin
        busy_o <= 1'b0;
      end else if (busy_o && tick_i) begin
        if (count_q == threshold_i) begin
          busy_o <= 1'b0;
          done_o <= 1'b1;
        end else begin
          count_q <= count_q + 8'd1;
        end
      end
    end
  end
endmodule
