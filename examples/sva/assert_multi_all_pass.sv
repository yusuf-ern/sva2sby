module assert_multi_all_pass(input logic clk);
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

	property p0;
		@(posedge clk) req |=> mid;
	endproperty

	property p1;
		@(posedge clk) req |=> mid ##1 done;
	endproperty

	assert property (p0);
	assert property (p1);
endmodule
