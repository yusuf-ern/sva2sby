module assert_raw_delay_pass(input logic clk);
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

	property p;
		@(posedge clk) req |=> mid ##1 done;
	endproperty

	assert property (p);
endmodule
