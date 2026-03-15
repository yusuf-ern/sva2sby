module cover_disable_iff_hit(input logic clk);
	logic rst_n;
	logic [2:0] cnt;
	wire req;
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
	assign done = (cnt == 3'b010);

	property p_cov;
		@(posedge clk) disable iff (!rst_n) req ##1 done;
	endproperty

	cover property (p_cov);
endmodule
