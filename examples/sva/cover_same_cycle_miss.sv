module cover_same_cycle_miss(input logic clk);
	logic hit;

	initial hit = 1'b0;

	always @(posedge clk)
		hit <= 1'b0;

	property p_cov;
		@(posedge clk) hit;
	endproperty

	cover property (p_cov);
endmodule
