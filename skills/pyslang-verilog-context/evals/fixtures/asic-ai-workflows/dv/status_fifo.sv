module status_fifo (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        wr_en,
    input  logic [7:0]  wr_data,
    input  logic        rd_en,
    output logic [7:0]  rd_data,
    output logic        full,
    output logic        empty,
    output logic        overflow,
    output logic        underflow,
    output logic [2:0]  level
);

logic [7:0] mem [0:3];
logic [1:0] wr_ptr_q;
logic [1:0] rd_ptr_q;

always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        wr_ptr_q  <= 2'd0;
        rd_ptr_q  <= 2'd0;
        level     <= 3'd0;
        rd_data   <= 8'h00;
        overflow  <= 1'b0;
        underflow <= 1'b0;
    end else begin
        overflow  <= 1'b0;
        underflow <= 1'b0;

        if (wr_en) begin
            if (!full) begin
                mem[wr_ptr_q] <= wr_data;
                wr_ptr_q      <= wr_ptr_q + 2'd1;
                level         <= level + 3'd1;
            end else begin
                overflow <= 1'b1;
            end
        end

        if (rd_en) begin
            if (!empty) begin
                rd_data   <= mem[rd_ptr_q];
                rd_ptr_q  <= rd_ptr_q + 2'd1;
                level     <= level - 3'd1;
            end else begin
                underflow <= 1'b1;
            end
        end
    end
end

assign full  = (level == 3'd4);
assign empty = (level == 3'd0);

endmodule
