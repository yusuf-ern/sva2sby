module cover_named_delay_miss(input logic clk);
	logic [1:0] cnt;
	wire req;
	wire never_done;

	initial cnt = 2'b00;

	always @(posedge clk)
		cnt <= cnt + 2'b01;

	assign req = (cnt == 2'b00);
	assign never_done = 1'b0;

	sequence s_req_done;
		req ##1 never_done;
	endsequence

	property p_cov;
		@(posedge clk) s_req_done;
	endproperty

	cover property (p_cov);
endmodule
