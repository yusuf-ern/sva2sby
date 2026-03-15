module assert_named_delay_fail(input logic clk);
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

	sequence s_done_mid;
		done ##1 mid;
	endsequence

	property p;
		@(posedge clk) req |=> s_done_mid;
	endproperty

	assert property (p);
endmodule
