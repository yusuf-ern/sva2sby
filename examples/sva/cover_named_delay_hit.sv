module cover_named_delay_hit(input logic clk);
	logic [1:0] cnt;
	wire req;
	wire done;

	initial cnt = 2'b00;

	always @(posedge clk)
		cnt <= cnt + 2'b01;

	assign req = (cnt == 2'b00);
	assign done = (cnt == 2'b01);

	sequence s_req_done;
		req ##1 done;
	endsequence

	property p_cov;
		@(posedge clk) s_req_done;
	endproperty

	cover property (p_cov);
endmodule
