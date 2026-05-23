module missing_intent_block (
    input  logic       clk,
    input  logic       rst_n,
    input  logic       enable,
    input  logic       start,
    output logic       busy,
    output logic       done
);

logic [1:0] work_q;

always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        work_q <= 2'd0;
        busy   <= 1'b0;
        done   <= 1'b0;
    end else begin
        done <= 1'b0;

        if (enable && start && !busy) begin
            busy   <= 1'b1;
            work_q <= 2'd2;
        end else if (busy && (work_q != 2'd0)) begin
            work_q <= work_q - 2'd1;
        end else if (busy) begin
            busy <= 1'b0;
            done <= 1'b1;
        end
    end
end

endmodule
