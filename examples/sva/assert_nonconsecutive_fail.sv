module assert_nonconsecutive_fail(input logic clk);
	logic [2:0] cnt;
	wire start;
	wire a;
	wire done;

	initial cnt = 3'd0;

	always @(posedge clk)
		cnt <= cnt + 3'd1;

	assign start = (cnt == 3'd0);
	assign a = 1'b0;
	assign done = (cnt == 3'd5);

	property p_nonconsecutive;
		@(posedge clk) start |=> a[=2] ##1 done;
	endproperty

	assert property (p_nonconsecutive);
endmodule
