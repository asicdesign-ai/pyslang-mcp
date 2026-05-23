`include "fifo_defs.svh"

package sync_fifo_pkg;

localparam int DEFAULT_DEPTH = `SYNC_FIFO_DEFAULT_DEPTH;

function automatic int ptr_width(input int depth);
    if (depth <= 1) begin
        return 1;
    end
    return $clog2(depth);
endfunction

function automatic int count_width(input int depth);
    if (depth <= 1) begin
        return 1;
    end
    return $clog2(depth + 1);
endfunction

endpackage
