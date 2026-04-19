module sync_fifo_mem #(
    parameter int WIDTH = 8,
    parameter int DEPTH = 4,
    parameter int PTR_W = (DEPTH <= 1) ? 1 : $clog2(DEPTH)
) (
    input  logic             clk,
    input  logic             wr_en_i,
    input  logic [PTR_W-1:0] wr_ptr_i,
    input  logic [PTR_W-1:0] rd_ptr_i,
    input  logic [WIDTH-1:0] wr_data_i,
    output logic [WIDTH-1:0] rd_data_o
);

logic [WIDTH-1:0] mem [0:DEPTH-1];

always_ff @(posedge clk) begin
    if (wr_en_i) begin
        mem[wr_ptr_i] <= wr_data_i;
    end
end

always_comb begin
    rd_data_o = mem[rd_ptr_i];
end

endmodule
