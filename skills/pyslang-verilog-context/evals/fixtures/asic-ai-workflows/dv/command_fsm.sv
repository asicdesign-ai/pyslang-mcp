module command_fsm (
    input  logic       clk,
    input  logic       rst_n,
    input  logic       cmd_valid,
    input  logic [1:0] cmd_code,
    output logic       busy,
    output logic       done,
    output logic       error_flag
);

typedef enum logic [1:0] {
    ST_IDLE = 2'd0,
    ST_BUSY = 2'd1,
    ST_DONE = 2'd2
} state_t;

state_t state_q;

always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        state_q    <= ST_IDLE;
        busy       <= 1'b0;
        done       <= 1'b0;
        error_flag <= 1'b0;
    end else begin
        done       <= 1'b0;
        error_flag <= 1'b0;

        unique case (state_q)
            ST_IDLE: begin
                busy <= 1'b0;
                if (cmd_valid && (cmd_code == 2'b01)) begin
                    state_q <= ST_BUSY;
                    busy    <= 1'b1;
                end else if (cmd_valid) begin
                    error_flag <= 1'b1;
                end
            end

            ST_BUSY: begin
                busy <= 1'b1;
                if (cmd_valid && (cmd_code == 2'b10)) begin
                    state_q <= ST_DONE;
                    busy    <= 1'b0;
                    done    <= 1'b1;
                end else if (cmd_valid && (cmd_code == 2'b11)) begin
                    state_q <= ST_IDLE;
                    busy    <= 1'b0;
                end else if (cmd_valid) begin
                    error_flag <= 1'b1;
                end
            end

            default: begin
                state_q <= ST_IDLE;
                busy    <= 1'b0;
            end
        endcase
    end
end

endmodule
