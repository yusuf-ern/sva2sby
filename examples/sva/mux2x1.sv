module mux2x1(input logic clk, input logic sel, input logic a, input logic b, output logic out);
	always_ff @(posedge clk) begin
		if (sel)
			out <= a;
		else
			out <= b;
	end
//
	// Formal Assertion
	// The mux output should equal the previously sampled selected input.
	property mux_output_matches_selected_input;
		@(posedge clk) 1'b1 |-> a[*4] ##1 (out == $past(sel ? a : b))[*2];
	endproperty
	assert  property (mux_output_matches_selected_input);
	// Assumption: Constrain inputs in certain scenarios if needed (e.g., reset behavior)
	// assume property (my_condition);

	// Cover property (optional, to ensure the formal tool can reach specific states)
	// cover property (out_is_high_witness);

endmodule
