module leaf (
  input  logic in_data,
  output logic out_data
);
  assign out_data = in_data;
endmodule

module open_port_top (
  input logic in_data
);
  // out_data is intentionally left open -- this port connection has no
  // expression, which used to crash instance serialization during indexing.
  leaf u_leaf (
    .in_data (in_data),
    .out_data()
  );
endmodule
