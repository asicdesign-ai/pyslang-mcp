module register_pipe #(
    parameter WIDTH = 16
) (
    input  wire             clk,
    input  wire             rst_n,
    input  wire             valid_i,
    input  wire             stall_i,
    input  wire [WIDTH-1:0] data_i,
    output wire             valid_o,
    output wire [WIDTH-1:0] data_o
);

reg             valid_q;
reg [WIDTH-1:0] data_q;

always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        valid_q <= 1'b0;
        data_q  <= {WIDTH{1'b0}};
    end else if (!stall_i) begin
        valid_q <= valid_i;
        if (valid_i) begin
            data_q <= data_i;
        end else begin
            data_q <= {WIDTH{1'b0}};
        end
    end
end

assign valid_o = valid_q;
assign data_o  = data_q;

endmodule
