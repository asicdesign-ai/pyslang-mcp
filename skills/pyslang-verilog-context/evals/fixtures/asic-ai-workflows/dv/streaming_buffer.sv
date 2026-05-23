module streaming_buffer (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        in_valid,
    input  logic [7:0]  in_data,
    output logic        in_ready,
    output logic        out_valid,
    output logic [7:0]  out_data,
    input  logic        out_ready
);

logic       full_q;
logic [7:0] data_q;

assign in_ready  = !full_q || out_ready;
assign out_valid = full_q;
assign out_data  = data_q;

always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        full_q <= 1'b0;
        data_q <= 8'h00;
    end else begin
        if (in_valid && in_ready) begin
            data_q <= in_data;
            full_q <= 1'b1;
        end else if (out_ready && out_valid) begin
            full_q <= 1'b0;
        end
    end
end

endmodule
