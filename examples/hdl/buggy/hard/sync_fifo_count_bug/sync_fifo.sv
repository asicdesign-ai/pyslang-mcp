`include "fifo_defs.svh"
import sync_fifo_pkg::*;

module sync_fifo #(
    parameter int WIDTH = 8,
    parameter int DEPTH = DEFAULT_DEPTH,
    parameter int PTR_W = ptr_width(DEPTH),
    parameter int COUNT_W = count_width(DEPTH)
) (
    input  logic               clk,
    input  logic               rst_n,
    input  logic               push_i,
    input  logic               pop_i,
    input  logic [WIDTH-1:0]   data_i,
    output logic [WIDTH-1:0]   data_o,
    output logic               full_o,
    output logic               empty_o,
    output logic [COUNT_W-1:0] level_o
);

localparam logic [PTR_W-1:0]   LAST_PTR   = PTR_W'(DEPTH - 1);
localparam logic [PTR_W-1:0]   PTR_ONE    = {{(PTR_W - 1){1'b0}}, 1'b1};
localparam logic [COUNT_W-1:0] FULL_COUNT = COUNT_W'(DEPTH);
localparam logic [COUNT_W-1:0] COUNT_ONE  = {{(COUNT_W - 1){1'b0}}, 1'b1};

logic [PTR_W-1:0] wr_ptr_q;
logic [PTR_W-1:0] rd_ptr_q;
logic [COUNT_W-1:0] count_q;
logic push_fire;
logic pop_fire;

always_comb begin
    full_o    = (count_q == FULL_COUNT);
    empty_o   = (count_q == '0);
    level_o   = count_q;
    push_fire = push_i && !full_o;
    pop_fire  = pop_i && !empty_o;
end

always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        wr_ptr_q <= '0;
        rd_ptr_q <= '0;
        count_q  <= '0;
    end else begin
        if (push_fire) begin
            if (wr_ptr_q == LAST_PTR) begin
                wr_ptr_q <= '0;
            end else begin
                wr_ptr_q <= wr_ptr_q + PTR_ONE;
            end
        end

        if (pop_fire) begin
            if (rd_ptr_q == LAST_PTR) begin
                rd_ptr_q <= '0;
            end else begin
                rd_ptr_q <= rd_ptr_q + PTR_ONE;
            end
        end

        if (push_fire) begin
            count_q <= count_q + COUNT_ONE;
        end else if (pop_fire) begin
            count_q <= count_q - COUNT_ONE;
        end
    end
end

sync_fifo_mem #(
    .WIDTH(WIDTH),
    .DEPTH(DEPTH),
    .PTR_W(PTR_W)
) u_sync_fifo_mem (
    .clk(clk),
    .wr_en_i(push_fire),
    .wr_ptr_i(wr_ptr_q),
    .rd_ptr_i(rd_ptr_q),
    .wr_data_i(data_i),
    .rd_data_o(data_o)
);

endmodule
