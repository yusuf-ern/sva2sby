module assert_goto_fail(input logic clk);
	logic [2:0] cnt;
	wire start;
	wire a;
	wire done;

	initial cnt = 3'd0;

	always @(posedge clk)
		cnt <= cnt + 3'd1;

	assign start = (cnt == 3'd0);
	assign a = (cnt == 3'd1);
	assign done = (cnt == 3'd4);

	property p_goto;
		@(posedge clk) start |=> a[->2] ##1 done;
	endproperty

	assert property (p_goto);
endmodule
