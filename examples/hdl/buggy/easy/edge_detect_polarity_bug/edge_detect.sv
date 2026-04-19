module edge_detect (
    input  logic clk,
    input  logic rst_n,
    input  logic signal_i,
    output logic rise_pulse_o,
    output logic fall_pulse_o,
    output logic either_pulse_o
);

logic signal_q;

always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        signal_q <= 1'b0;
    end else begin
        signal_q <= signal_i;
    end
end

always_comb begin
    rise_pulse_o   = !signal_i && signal_q;
    fall_pulse_o   = !signal_i && signal_q;
    either_pulse_o = rise_pulse_o || fall_pulse_o;
end

endmodule
