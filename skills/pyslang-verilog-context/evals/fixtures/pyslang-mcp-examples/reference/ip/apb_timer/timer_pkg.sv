`include "apb_timer_defs.svh"

package timer_pkg;

localparam logic [7:0] DEFAULT_PRESCALE = `APB_TIMER_DEFAULT_PRESCALE;
localparam logic [15:0] DEFAULT_PERIOD = 16'd100;

typedef struct packed {
    logic enable;
    logic irq_enable;
} timer_ctrl_t;

endpackage
