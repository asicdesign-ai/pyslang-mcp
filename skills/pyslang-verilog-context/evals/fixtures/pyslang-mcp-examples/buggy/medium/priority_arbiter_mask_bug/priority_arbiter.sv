module priority_arbiter #(
    parameter int WIDTH = 4,
    parameter int INDEX_W = (WIDTH <= 1) ? 1 : $clog2(WIDTH)
) (
    input  logic [WIDTH-1:0] request_i,
    input  logic [WIDTH-1:0] mask_i,
    output logic [WIDTH-1:0] grant_o,
    output logic             any_grant_o,
    output logic [INDEX_W-1:0] grant_index_o
);

logic [WIDTH-1:0] eligible_req;
int idx;

always_comb begin
    eligible_req  = request_i & ~mask_i;
    grant_o       = '0;
    grant_index_o = '0;

    for (idx = WIDTH - 1; idx >= 0; idx--) begin
        if ((grant_o == '0) && eligible_req[idx]) begin
            grant_o[idx]  = 1'b1;
            grant_index_o = idx[INDEX_W-1:0];
        end
    end

    any_grant_o = |grant_o;
end

endmodule
