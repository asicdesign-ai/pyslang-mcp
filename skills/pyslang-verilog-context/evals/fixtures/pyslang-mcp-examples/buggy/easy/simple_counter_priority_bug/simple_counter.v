module simple_counter #(
    parameter WIDTH = 8
) (
    input  wire             clk,
    input  wire             rst_n,
    input  wire             enable_i,
    input  wire             clear_i,
    input  wire             load_i,
    input  wire [WIDTH-1:0] load_value_i,
    output wire [WIDTH-1:0] count_o,
    output wire             tick_o
);

reg [WIDTH-1:0] count_q;

always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        count_q <= {WIDTH{1'b0}};
    end else if (enable_i) begin
        count_q <= count_q + {{(WIDTH-1){1'b0}}, 1'b1};
    end else if (load_i) begin
        count_q <= load_value_i;
    end else if (clear_i) begin
        count_q <= {WIDTH{1'b0}};
    end
end

assign count_o = count_q;
assign tick_o = enable_i && !clear_i && !load_i && (count_q == {WIDTH{1'b1}});

endmodule
