module tap_delay_line #(
    parameter int WIDTH = 8,
    parameter int DEPTH = 4
) (
    input  logic                  clk,
    input  logic                  rst_n,
    input  logic                  shift_i,
    input  logic [WIDTH-1:0]      data_i,
    output logic [DEPTH*WIDTH-1:0] taps_o
);

logic [WIDTH-1:0] stage_q [0:DEPTH-1];
integer stage_idx;
genvar tap_idx;

always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        for (stage_idx = 0; stage_idx < DEPTH; stage_idx++) begin
            stage_q[stage_idx] <= '0;
        end
    end else if (shift_i) begin
        stage_q[0] <= data_i;
        for (stage_idx = 1; stage_idx < DEPTH; stage_idx++) begin
            stage_q[stage_idx] <= stage_q[stage_idx - 1];
        end
    end
end

generate
    for (tap_idx = 0; tap_idx < DEPTH; tap_idx++) begin : gen_taps
        assign taps_o[tap_idx*WIDTH +: WIDTH] = stage_q[tap_idx];
    end
endgenerate

endmodule
