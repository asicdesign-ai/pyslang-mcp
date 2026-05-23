module load_store_command_processor (
    input  logic        clk_i,
    input  logic        rst_n,
    input  logic        store_valid_i,
    input  logic [1:0]  store_addr_i,
    input  logic [31:0] store_data_i,
    input  logic        downstream_ready_i,
    output logic [31:0] work_data_o,
    output logic        work_valid_o
);
  logic [3:0][31:0] mem_q, mem_d;
  logic [3:0]       mem_valid_q, mem_valid_d;
  logic [31:0]      work_reg_q, work_reg_d;
  logic             work_valid_q, work_valid_d;
  logic [1:0]       load_addr;
  logic             load_pending;
  logic             load_fire;

  // Deterministic load policy: choose the lowest-address occupied slot.
  always_comb begin
    load_pending = 1'b0;
    load_addr    = 2'd0;

    unique casez (mem_valid_q)
      4'b???1: begin
        load_pending = 1'b1;
        load_addr    = 2'd0;
      end
      4'b??10: begin
        load_pending = 1'b1;
        load_addr    = 2'd1;
      end
      4'b?100: begin
        load_pending = 1'b1;
        load_addr    = 2'd2;
      end
      4'b1000: begin
        load_pending = 1'b1;
        load_addr    = 2'd3;
      end
      default: begin
        load_pending = 1'b0;
        load_addr    = 2'd0;
      end
    endcase
  end

  assign load_fire = load_pending && downstream_ready_i;

  always_comb begin
    mem_d       = mem_q;
    mem_valid_d = mem_valid_q;
    work_reg_d  = work_reg_q;
    work_valid_d = work_valid_q;

    if (work_valid_q && downstream_ready_i) begin
      work_valid_d = 1'b0;
    end

    if (load_fire) begin
      work_reg_d            = mem_q[load_addr];
      work_valid_d          = 1'b1;
      mem_valid_d[load_addr] = 1'b0;
    end

    if (store_valid_i) begin
      mem_d[store_addr_i]       = store_data_i;
      mem_valid_d[store_addr_i] = 1'b1;
    end
  end

  always_ff @(posedge clk_i or negedge rst_n) begin
    if (!rst_n) begin
      mem_q       <= '0;
      mem_valid_q <= '0;
      work_reg_q  <= '0;
      work_valid_q <= 1'b0;
    end else begin
      mem_q       <= mem_d;
      mem_valid_q <= mem_valid_d;
      work_reg_q  <= work_reg_d;
      work_valid_q <= work_valid_d;
    end
  end

  assign work_data_o  = work_reg_q;
  assign work_valid_o = work_valid_q;
endmodule
