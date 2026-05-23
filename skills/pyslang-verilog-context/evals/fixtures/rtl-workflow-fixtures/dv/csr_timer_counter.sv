module timer_counter (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        cfg_enable,
    input  logic        cfg_load,
    input  logic [7:0]  cfg_data,
    input  logic        clear_irq,
    input  logic [7:0]  terminal_count,
    output logic [7:0]  count_value,
    output logic        irq
);

logic        enable_q;
logic [7:0]  count_q;

always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        enable_q <= 1'b0;
        count_q  <= 8'h00;
        irq      <= 1'b0;
    end else begin
        enable_q <= cfg_enable;

        if (cfg_load) begin
            count_q <= cfg_data;
        end else if (enable_q) begin
            count_q <= count_q + 8'd1;
        end

        if (clear_irq) begin
            irq <= 1'b0;
        end else if (enable_q && (count_q == terminal_count)) begin
            irq <= 1'b1;
        end
    end
end

assign count_value = count_q;

endmodule
