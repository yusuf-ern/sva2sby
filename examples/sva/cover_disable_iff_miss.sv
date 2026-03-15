module cover_disable_iff_miss(input logic clk);
	logic rst_n;
	wire req;
	wire never_done;

	initial rst_n = 1'b1;

	always @(posedge clk)
		rst_n <= 1'b1;

	assign req = 1'b0;
	assign never_done = 1'b0;

	property p_cov;
		@(posedge clk) disable iff (!rst_n) req ##1 never_done;
	endproperty

	cover property (p_cov);
endmodule
