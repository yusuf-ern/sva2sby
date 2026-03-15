module assert_nonconsecutive_pass(input logic clk);
	logic [2:0] cnt;
	wire start;
	wire a;
	wire done;

	initial cnt = 3'd0;

	always @(posedge clk)
		cnt <= cnt + 3'd1;

	assign start = (cnt == 3'd0);
	assign a = (cnt == 3'd1) || (cnt == 3'd3);
	assign done = (cnt == 3'd5);

	property p_nonconsecutive;
		@(posedge clk) start |=> a[=2] ##1 done;
	endproperty

	assert property (p_nonconsecutive);
endmodule
