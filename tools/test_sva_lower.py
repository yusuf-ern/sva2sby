#!/usr/bin/env python3
"""Basic tests for the prototype SVA lowerer."""

from __future__ import annotations

import unittest

from sva_lower import lower_text


class SvaLowerTests(unittest.TestCase):
    def test_lowers_assert_assume_cover(self) -> None:
        source = """
module top(
    input logic clk,
    input logic rst_n,
    input logic req,
    input logic ack,
    input logic done,
    input logic env_ok
);
sequence s_req_ack;
    req ##1 ack;
endsequence

property p_assert;
    @(posedge clk) disable iff (!rst_n) s_req_ack |=> done;
endproperty

property p_assume;
    @(posedge clk) disable iff (!rst_n) req |-> env_ok;
endproperty

property p_cover;
    @(posedge clk) disable iff (!rst_n) s_req_ack ##2 done;
endproperty

assert property (p_assert);
assume property (p_assume);
cover property (p_cover);
endmodule
"""
        lowered = lower_text(source)
        self.assertIn("// sva_lower: removed sequence s_req_ack", lowered)
        self.assertIn("// sva_lower: lowered assert property (p_assert)", lowered)
        self.assertIn("// sva_lower: lowered assume property (p_assume)", lowered)
        self.assertIn("// sva_lower: lowered cover property (p_cover)", lowered)
        self.assertIn("assert ((done));", lowered)
        self.assertIn("assume ((env_ok));", lowered)
        self.assertIn("cover (1'b1);", lowered)
        self.assertIn("reg __sva_assert_p_assert_ant_t0;", lowered)
        self.assertIn("reg [2:0] __sva_cover_p_cover_seq_t0;", lowered)

    def test_zero_cycle_sequence_assert_is_allowed(self) -> None:
        source = """
module top(input logic clk, input logic a);
property p_same_cycle;
    @(posedge clk) a;
endproperty
assert property (p_same_cycle);
endmodule
"""
        lowered = lower_text(source)
        self.assertIn("if (1'b1) assert ((a));", lowered)

    def test_multicycle_bare_assert_is_rejected(self) -> None:
        source = """
module top(input logic clk, input logic a, input logic b);
property p_bad;
    @(posedge clk) a ##1 b;
endproperty
assert property (p_bad);
endmodule
"""
        with self.assertRaisesRegex(ValueError, "multi-cycle bare sequence"):
            lower_text(source)

    def test_delayed_implication_without_disable_initializes_history(self) -> None:
        source = """
module top(input logic clk, input logic req, input logic mid, input logic done);
property p_delay;
    @(posedge clk) req |=> mid ##1 done;
endproperty
assert property (p_delay);
endmodule
"""
        lowered = lower_text(source)
        self.assertIn("\tinitial begin\n", lowered)
        self.assertIn("\t\t__sva_assert_p_delay_con_t0 <= 1'b0;\n", lowered)
        self.assertIn("\t\t__sva_assert_p_delay_launch_hist <= 2'b0;\n", lowered)
        self.assertIn("\t\t__sva_assert_p_delay_past_valid <= 2'b0;\n", lowered)
        self.assertIn("assert (__sva_assert_p_delay_con_t0 == $past((mid)));", lowered)
        self.assertIn(
            "assert (__sva_assert_p_delay_launch_hist[1] == $past(((req)), 2));",
            lowered,
        )

    def test_lowers_default_clocking_inline_properties_and_cover_chain(self) -> None:
        source = """
module top(input logic clk, input logic rst_n, input logic a, input logic b, input logic c);
default clocking @(posedge clk); endclocking
default disable iff (!rst_n);

assert property (a |-> b [*] ##1 c);
cover property (a ##[+] b ##[+] c);
endmodule
"""
        lowered = lower_text(source)
        self.assertIn("// sva_lower: removed default clocking clk", lowered)
        self.assertIn("// sva_lower: removed default disable iff (!rst_n)", lowered)
        self.assertIn("reg __sva_assert_anon_0_wait;", lowered)
        self.assertIn("if (__sva_assert_anon_0_wait && !(c)) assert ((b));", lowered)
        self.assertIn("reg [1:0] __sva_cover_anon_1_stage;", lowered)
        self.assertIn("if ((__sva_cover_anon_1_stage == 2'd2) && (c)) cover (1'b1);", lowered)

    def test_lowers_inline_property_with_explicit_clock(self) -> None:
        source = """
module top(input logic clk, input logic a);
assert property (@(posedge clk) a);
endmodule
"""
        lowered = lower_text(source)
        self.assertIn("// sva_lower: lowered assert property (anon_0)", lowered)
        self.assertIn("always @(posedge clk) begin", lowered)
        self.assertIn("if (1'b1) assert ((a));", lowered)

    def test_lowers_implication_with_leading_delay_in_consequent(self) -> None:
        source = """
module top(input logic clk, input logic a, input logic b);
property p_delay;
    @(posedge clk) a |-> ##1 b;
endproperty
assert property (p_delay);
endmodule
"""
        lowered = lower_text(source)
        self.assertIn("// sva_lower: lowered assert property (p_delay)", lowered)
        self.assertIn("reg __sva_assert_p_delay_con_t0;", lowered)
        self.assertIn("reg __sva_assert_p_delay_launch_hist;", lowered)
        self.assertIn("if (__sva_assert_p_delay_launch_hist) assert (__sva_assert_p_delay_con_t0 && (b));", lowered)

    def test_lowers_implication_with_ranged_delay_in_consequent(self) -> None:
        source = """
module top(input logic clk, input logic a, input logic b);
property p_range;
    @(posedge clk) a |-> ##[1:3] b;
endproperty
assert property (p_range);
endmodule
"""
        lowered = lower_text(source)
        self.assertIn("reg [2:0] __sva_assert_p_range_pending;", lowered)
        self.assertIn("reg [2:0] __sva_assert_p_range_past_valid;", lowered)
        self.assertIn("if (__sva_assert_p_range_pending[2]) assert (b);", lowered)
        self.assertIn("__sva_assert_p_range_pending <= {((__sva_assert_p_range_pending[1]) && !(b))", lowered)

    def test_lowers_implication_with_bounded_repetition(self) -> None:
        source = """
module top(input logic clk, input logic start, input logic a);
property p_repeat;
    @(posedge clk) start |-> a[*2:3];
endproperty
assert property (p_repeat);
endmodule
"""
        lowered = lower_text(source)
        self.assertIn("reg [1:0] __sva_assert_p_repeat_launch_hist;", lowered)
        self.assertIn("$past((a), 2)", lowered)
        self.assertIn("((a) && $past((a)) && $past((a), 2))", lowered)

    def test_lowers_nonterminal_bounded_repetition_implication(self) -> None:
        source = """
module top(input logic clk, input logic start, input logic a, input logic b);
property p_repeat_tail;
    @(posedge clk) start |-> a[*2:3] ##1 b;
endproperty
assert property (p_repeat_tail);
endmodule
"""
        lowered = lower_text(source)
        self.assertIn("reg [2:0] __sva_assert_p_repeat_tail_launch_hist;", lowered)
        self.assertIn("$past((b))", lowered)
        self.assertIn("&& (b)", lowered)

    def test_ignores_commented_out_sva(self) -> None:
        source = """
module top(input logic clk, input logic a, input logic b);
// property old_p;
//     @(posedge clk) a |-> ##1 b;
// endproperty
/* assert property (old_p); */
property p_ok;
    @(posedge clk) a |-> b;
endproperty
assert property (p_ok);
endmodule
"""
        lowered = lower_text(source)
        self.assertNotIn("old_p", lowered)
        self.assertIn("// sva_lower: lowered assert property (p_ok)", lowered)
        self.assertIn("if ((a)) assert ((b));", lowered)


if __name__ == "__main__":
    unittest.main()
