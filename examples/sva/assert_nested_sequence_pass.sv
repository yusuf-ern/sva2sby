module assert_nested_sequence_pass(input logic clk);
	logic [1:0] cnt;
	wire req;
	wire mid;
	wire done;

	initial cnt = 2'b00;

	always @(posedge clk)
		cnt <= cnt + 2'b01;

	assign req = (cnt == 2'b00);
	assign mid = (cnt == 2'b01);
	assign done = (cnt == 2'b10);

	sequence s_done;
		done;
	endsequence

	sequence s_mid_done;
		mid ##1 s_done;
	endsequence

	property p;
		@(posedge clk) req |=> s_mid_done;
	endproperty

	assert property (p);
endmodule
