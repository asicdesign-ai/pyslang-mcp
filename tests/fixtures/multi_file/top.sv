`include "defs.svh"
import types_pkg::*;

module top (
  input logic clk
);
  data_t payload;
  logic [`WIDTH-1:0] widened;

  child u_child(
    .in_data(payload),
    .out_data(widened)
  );
endmodule
