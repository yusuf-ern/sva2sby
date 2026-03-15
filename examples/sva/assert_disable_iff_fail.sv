module assert_disable_iff_fail(input logic clk);
	logic rst_n;
	logic [2:0] cnt;
	wire req;
	wire mid;
	wire done;

	initial begin
		rst_n = 1'b0;
		cnt = 3'b000;
	end

	always @(posedge clk) begin
		rst_n <= 1'b1;
		cnt <= cnt + 3'b001;
	end

	assign req = (cnt == 3'b001);
	assign mid = (cnt == 3'b010);
	assign done = (cnt == 3'b100);

	property p;
		@(posedge clk) disable iff (!rst_n) req |=> mid ##1 done;
	endproperty

	assert property (p);
endmodule
