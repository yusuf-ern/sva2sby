module cover_same_cycle_hit(input logic clk);
	logic [1:0] cnt;
	wire hit;

	initial cnt = 2'b00;

	always @(posedge clk)
		cnt <= cnt + 2'b01;

	assign hit = (cnt == 2'b10);

	property p_cov;
		@(posedge clk) hit;
	endproperty

	cover property (p_cov);
endmodule
