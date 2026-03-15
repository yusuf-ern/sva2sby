module assume_assert_overlap_fail(input logic clk, input logic req, input logic ack);
	property p_env;
		@(posedge clk) req |-> ack;
	endproperty

	property p_safe;
		@(posedge clk) req |=> ack;
	endproperty

	assume property (p_env);
	assert property (p_safe);
endmodule
