module assert_repeat_tail_pass(input logic clk);
	logic [1:0] cnt;
	wire start;
	wire a;
	wire b;

	initial cnt = 2'b00;

	always @(posedge clk)
		cnt <= cnt + 2'b01;

	assign start = (cnt == 2'b00);
	assign a = (cnt == 2'b01) || (cnt == 2'b10);
	assign b = (cnt == 2'b11);

	property p_repeat_tail;
		@(posedge clk) start |=> a[*2:3] ##1 b;
	endproperty
	assert property (p_repeat_tail);
endmodule
