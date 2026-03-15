module assert_nested_sequence_fail(input logic clk);
	logic [1:0] cnt;
	wire req;
	wire mid;
	wire never_done;

	initial cnt = 2'b00;

	always @(posedge clk)
		cnt <= cnt + 2'b01;

	assign req = (cnt == 2'b00);
	assign mid = (cnt == 2'b01);
	assign never_done = 1'b0;

	sequence s_done;
		never_done;
	endsequence

	sequence s_mid_done;
		mid ##1 s_done;
	endsequence

	property p;
		@(posedge clk) req |=> s_mid_done;
	endproperty

	assert property (p);
endmodule
