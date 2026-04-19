import timer_pkg::*;

module timer_core (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        enable_i,
    input  logic        irq_enable_i,
    input  logic        clear_irq_i,
    input  logic [7:0]  prescale_i,
    input  logic [15:0] period_i,
    output logic [15:0] count_o,
    output logic        irq_o
);

logic [7:0] prescale_q;
logic tick;

always_comb begin
    tick = enable_i && (prescale_q == prescale_i);
end

always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        prescale_q <= '0;
        count_o    <= '0;
        irq_o      <= 1'b0;
    end else begin
        if (!enable_i) begin
            prescale_q <= '0;
            count_o    <= '0;
        end else if (tick) begin
            prescale_q <= '0;
            if (count_o == period_i) begin
                count_o <= '0;
                if (irq_enable_i) begin
                    irq_o <= 1'b1;
                end
            end else begin
                count_o <= count_o + 16'd1;
            end
        end else begin
            prescale_q <= prescale_q + 8'd1;
        end

        if (clear_irq_i) begin
            irq_o <= 1'b0;
        end
    end
end

endmodule
