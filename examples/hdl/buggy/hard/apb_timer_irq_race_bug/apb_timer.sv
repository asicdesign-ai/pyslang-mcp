import timer_pkg::*;

module apb_timer (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        psel_i,
    input  logic        penable_i,
    input  logic        pwrite_i,
    input  logic [7:0]  paddr_i,
    input  logic [31:0] pwdata_i,
    output logic [31:0] prdata_o,
    output logic        pready_o,
    output logic        pslverr_o,
    output logic        irq_o
);

localparam logic [7:0] ADDR_CTRL     = 8'h00;
localparam logic [7:0] ADDR_PRESCALE = 8'h04;
localparam logic [7:0] ADDR_PERIOD   = 8'h08;
localparam logic [7:0] ADDR_STATUS   = 8'h0c;

timer_ctrl_t ctrl_q;
logic [7:0] prescale_q;
logic [15:0] period_q;
logic [15:0] count_s;
logic clear_irq_pulse;
logic write_en;

assign pready_o        = 1'b1;
assign pslverr_o       = 1'b0;
assign write_en        = psel_i && penable_i && pwrite_i;
assign clear_irq_pulse = write_en && (paddr_i == ADDR_CTRL) && pwdata_i[2];

always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        ctrl_q     <= '{enable: 1'b0, irq_enable: 1'b0};
        prescale_q <= DEFAULT_PRESCALE;
        period_q   <= DEFAULT_PERIOD;
    end else if (write_en) begin
        case (paddr_i)
            ADDR_CTRL: begin
                ctrl_q.enable     <= pwdata_i[0];
                ctrl_q.irq_enable <= pwdata_i[1];
            end
            ADDR_PRESCALE: prescale_q <= pwdata_i[7:0];
            ADDR_PERIOD: period_q <= pwdata_i[15:0];
            default: begin end
        endcase
    end
end

timer_core u_timer_core (
    .clk(clk),
    .rst_n(rst_n),
    .enable_i(ctrl_q.enable),
    .irq_enable_i(ctrl_q.irq_enable),
    .clear_irq_i(clear_irq_pulse),
    .prescale_i(prescale_q),
    .period_i(period_q),
    .count_o(count_s),
    .irq_o(irq_o)
);

always_comb begin
    prdata_o = '0;
    case (paddr_i)
        ADDR_CTRL: begin
            prdata_o[0] = ctrl_q.enable;
            prdata_o[1] = ctrl_q.irq_enable;
        end
        ADDR_PRESCALE: prdata_o[7:0] = prescale_q;
        ADDR_PERIOD: prdata_o[15:0] = period_q;
        ADDR_STATUS: begin
            prdata_o[0]     = irq_o;
            prdata_o[31:16] = count_s;
        end
        default: prdata_o = '0;
    endcase
end

endmodule
