module assume_assert_named_delay(
	input logic clk,
	input logic req,
	input logic mid,
	input logic done
);
	sequence s_mid_done;
		mid ##1 done;
	endsequence

	property p_env;
		@(posedge clk) req |=> s_mid_done;
	endproperty

	property p_safe;
		@(posedge clk) req |=> s_mid_done;
	endproperty

	assume property (p_env);
	assert property (p_safe);
endmodule
