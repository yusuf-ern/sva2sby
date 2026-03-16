#!/usr/bin/env python3
"""Tests for the .sby staging path in sva_sby.py."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sva_sby import (
    build_ebmc_task_configs,
    normalize_ebmc_text,
    prepare_sby,
    source_requires_ebmc,
)


class SvaSbyTests(unittest.TestCase):
    def test_source_requires_ebmc_for_full_sva_operators(self) -> None:
        self.assertFalse(
            source_requires_ebmc(
                """module top(input logic clk, input logic a, input logic b);
assert property (@(posedge clk) a |-> b[->2]);
endmodule
"""
            )
        )
        self.assertFalse(
            source_requires_ebmc(
                """module top(input logic clk, input logic a, input logic b);
assert property (@(posedge clk) a |-> b[=2]);
endmodule
"""
            )
        )
        self.assertFalse(
            source_requires_ebmc(
                """module top(input logic clk, input logic a, input logic b);
assert property (@(posedge clk) a |-> b[*2:3] ##1 b);
endmodule
"""
            )
        )
        self.assertFalse(
            source_requires_ebmc(
                """module top(input logic clk, input logic a);
assert property (@(posedge clk) $rose(a) |=> a);
endmodule
"""
            )
        )

    def test_normalize_ebmc_text_expands_default_clocking_and_disable(self) -> None:
        normalized = normalize_ebmc_text(
            """module top(input logic clock, input logic reset, input logic a, input logic b);
default clocking @(posedge clock); endclocking
default disable iff (reset);
assert property (a |=> b);
endmodule
"""
        )
        self.assertIn("// sva_sby: removed default clocking clock", normalized)
        self.assertIn("// sva_sby: removed default disable iff (reset)", normalized)
        self.assertIn("assert property (@(posedge clock) disable iff (reset) a |=> b);", normalized)

    def test_prepare_sby_preserves_mode_and_engines(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_dir = root / "src"
            source_dir.mkdir()
            workdir = root / "work"

            sv_path = source_dir / "demo.sv"
            sv_path.write_text(
                """module demo(input logic clk, input logic a, input logic b);
property p;
    @(posedge clk) a |=> b;
endproperty
assert property (p);
endmodule
"""
            )

            sby_path = source_dir / "demo.sby"
            sby_path.write_text(
                """[options]
mode prove
depth 7

[engines]
smtbmc yices

[script]
read -formal -sv demo.sv
prep -top demo

[files]
demo.sv
"""
            )

            generated = prepare_sby(sby_path, workdir)
            generated_text = generated.read_text()

            self.assertIn("mode prove", generated_text)
            self.assertIn("depth 7", generated_text)
            self.assertIn("smtbmc yices", generated_text)
            self.assertIn("read -formal -sv demo.sv", generated_text)
            self.assertIn("files/demo.sv", generated_text)

            lowered = workdir / "files" / "demo.sv"
            self.assertTrue(lowered.exists())
            lowered_text = lowered.read_text()
            self.assertIn("`ifdef FORMAL", lowered_text)
            self.assertIn("assert (", lowered_text)

    def test_prepare_sby_supports_tasks_aliases_and_inline_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_dir = root / "src"
            nested_dir = source_dir / "rtl"
            nested_dir.mkdir(parents=True)
            workdir = root / "work"

            aliased_sv = nested_dir / "aliased.sv"
            aliased_sv.write_text(
                """module aliased(input logic clk, input logic a, input logic b);
property p_alias;
    @(posedge clk) a |=> b;
endproperty
assert property (p_alias);
endmodule
"""
            )

            sby_path = source_dir / "tasks.sby"
            sby_path.write_text(
                """[tasks]
prove
cover

[options]
prove: mode prove
cover: mode cover
depth 4

[engines]
prove:
smtbmc yices
--
cover:
smtbmc boolector
--

[script]
prove: read -formal -sv rtl/aliased.sv
cover: read -formal -sv inline_demo.sv
prep -top aliased

[files]
prove: aliased.sv rtl/aliased.sv

[file inline_demo.sv]
module inline_demo(input logic clk, input logic a, input logic b);
property p_inline;
    @(posedge clk) a |=> b;
endproperty
assert property (p_inline);
endmodule
"""
            )

            generated = prepare_sby(sby_path, workdir)
            generated_text = generated.read_text()

            self.assertIn("[tasks]", generated_text)
            self.assertIn("prove: aliased.sv files/aliased.sv", generated_text)
            self.assertIn("prove: read -formal -sv aliased.sv", generated_text)
            self.assertIn("cover: read -formal -sv inline_demo.sv", generated_text)
            self.assertIn("smtbmc yices", generated_text)
            self.assertIn("smtbmc boolector", generated_text)
            self.assertIn("`ifdef FORMAL", generated_text)
            self.assertIn("assert (", generated_text)

            lowered_alias = workdir / "files" / "aliased.sv"
            self.assertTrue(lowered_alias.exists())
            lowered_alias_text = lowered_alias.read_text()
            self.assertIn("`ifdef FORMAL", lowered_alias_text)
            self.assertIn("assert (", lowered_alias_text)

    def test_prepare_sby_lowers_goto_repetition_with_task_depth(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_dir = root / "src"
            source_dir.mkdir()
            workdir = root / "work"

            (source_dir / "goto_demo.sv").write_text(
                """module goto_demo(input logic clk, input logic start, input logic a, input logic done);
property p;
    @(posedge clk) start |=> a[->2] ##1 done;
endproperty
assert property (p);
endmodule
"""
            )
            sby_path = source_dir / "goto_demo.sby"
            sby_path.write_text(
                """[tasks]
prove

[options]
prove: mode prove
depth 6

[engines]
smtbmc

[script]
read -formal -sv goto_demo.sv
prep -top goto_demo

[files]
goto_demo.sv
"""
            )

            generated = prepare_sby(sby_path, workdir)
            staged = (workdir / "files" / "goto_demo.sv").read_text()
            generated_text = generated.read_text()
            self.assertIn("`ifdef FORMAL", staged)
            self.assertIn("reg [6:0] __sva_assert_p_st2;", staged)
            self.assertIn("__sva_assert_p_st2[0]", staged)
            self.assertNotIn("[->2]", staged)
            self.assertIn("prove: depth 12", generated_text)

    def test_prepare_sby_leaves_unsupported_inline_property_files_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_dir = root / "src"
            source_dir.mkdir()
            workdir = root / "work"

            sv_path = source_dir / "live_demo.sv"
            original_text = """module live_demo(input logic clk, input logic done);
`ifdef FORMAL
always @(posedge clk) begin
    assert property (s_eventually done);
end
`endif
endmodule
"""
            sv_path.write_text(original_text)

            sby_path = source_dir / "live_demo.sby"
            sby_path.write_text(
                """[options]
mode prove

[engines]
abc pdr

[script]
read -formal -sv live_demo.sv
prep -top live_demo

[files]
live_demo.sv
"""
            )

            prepare_sby(sby_path, workdir)
            staged = workdir / "files" / "live_demo.sv"
            self.assertEqual(staged.read_text(), original_text)

    def test_prepare_sby_leaves_multi_module_sva_files_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_dir = root / "src"
            source_dir.mkdir()
            workdir = root / "work"

            sv_path = source_dir / "multi.sv"
            original_text = """module helper;
endmodule

module top(input logic clk, input logic a);
`ifdef VERIFIC
property p;
    @(posedge clk) a;
endproperty
assert property (p);
`endif
endmodule
"""
            sv_path.write_text(original_text)

            sby_path = source_dir / "multi.sby"
            sby_path.write_text(
                """[options]
mode prove

[engines]
smtbmc

[script]
read -formal -sv multi.sv
prep -top top

[files]
multi.sv
"""
            )

            prepare_sby(sby_path, workdir)
            staged = workdir / "files" / "multi.sv"
            self.assertEqual(staged.read_text(), original_text)

    def test_build_ebmc_task_configs_extracts_task_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_dir = root / "src"
            source_dir.mkdir()
            workdir = root / "work"

            rtl = source_dir / "goto_demo.sv"
            rtl.write_text(
                """module goto_demo(input logic clk, input logic start, input logic a, input logic done);
property p;
    @(posedge clk) start |=> a[->2] ##1 done;
endproperty
assert property (p);
endmodule
"""
            )

            sby_path = source_dir / "goto_demo.sby"
            sby_path.write_text(
                """[tasks]
prove

[options]
prove: mode prove
depth 9

[engines]
prove: smtbmc yices

[script]
prove: read -formal -sv goto_demo.sv
prep -top goto_demo

[files]
goto_demo.sv
"""
            )

            configs = build_ebmc_task_configs(sby_path, workdir, ["prove"], None)
            self.assertEqual(len(configs), 1)
            config = configs[0]
            self.assertEqual(config.name, "prove")
            self.assertEqual(config.mode, "prove")
            self.assertEqual(config.depth, 9)
            self.assertEqual(config.top, "goto_demo")
            self.assertEqual(config.solver_flags, ["--yices"])
            self.assertEqual(config.method_flags, [])
            self.assertEqual(len(config.sources), 1)
            self.assertTrue(config.sources[0].exists())

    def test_build_ebmc_task_configs_uses_sby_default_depth(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_dir = root / "src"
            source_dir.mkdir()
            workdir = root / "work"

            (source_dir / "demo.sv").write_text("module demo(input logic clk); endmodule\n")
            sby_path = source_dir / "demo.sby"
            sby_path.write_text(
                """[options]
mode bmc

[engines]
smtbmc

[script]
read -formal -sv demo.sv
prep -top demo

[files]
demo.sv
"""
            )

            configs = build_ebmc_task_configs(sby_path, workdir, [], None)
            self.assertEqual(len(configs), 1)
            self.assertEqual(configs[0].depth, 20)

    def test_prepare_sby_leaves_labeled_property_files_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_dir = root / "src"
            source_dir.mkdir()
            workdir = root / "work"

            sv_path = source_dir / "labeled.sv"
            original_text = """module labeled(input logic clk, input logic a);
property p;
    @(posedge clk) a;
endproperty
foo: assert property (p);
endmodule
"""
            sv_path.write_text(original_text)

            sby_path = source_dir / "labeled.sby"
            sby_path.write_text(
                """[options]
mode prove

[engines]
smtbmc

[script]
read -formal -sv labeled.sv
prep -top labeled

[files]
labeled.sv
"""
            )

            prepare_sby(sby_path, workdir)
            staged = workdir / "files" / "labeled.sv"
            self.assertEqual(staged.read_text(), original_text)

    def test_prepare_sby_can_strip_read_verific(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_dir = root / "src"
            source_dir.mkdir()
            workdir = root / "work"

            sv_path = source_dir / "demo.sv"
            sv_path.write_text("module demo; endmodule\n")

            sby_path = source_dir / "demo.sby"
            sby_path.write_text(
                """[options]
mode bmc

[engines]
smtbmc

[script]
read -verific
read -sv demo.sv
prep -top demo

[files]
demo.sv
"""
            )

            generated = prepare_sby(sby_path, workdir, strip_verific=True)
            generated_text = generated.read_text()
            self.assertIn("# sva_sby: stripped read -verific", generated_text)
            self.assertIn("read -sv demo.sv", generated_text)

    def test_prepare_sby_marks_nested_staged_reads_as_formal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_dir = root / "src"
            source_dir.mkdir()
            workdir = root / "work"

            sv_path = source_dir / "orig.sv"
            sv_path.write_text(
                """module demo(input logic clk, input logic a, input logic b);
property p;
    @(posedge clk) a |=> b;
endproperty
assert property (p);
endmodule
"""
            )

            sby_path = source_dir / "demo.sby"
            sby_path.write_text(
                """[options]
mode bmc
depth 4

[engines]
smtbmc

[script]
read -sv orig.sv
prep -top demo

[files]
rtl/demo.sv orig.sv
"""
            )

            generated = prepare_sby(sby_path, workdir)
            generated_text = generated.read_text()
            self.assertIn("read -formal -sv rtl/demo.sv", generated_text)

    def test_prepare_sby_can_override_task_engine(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_dir = root / "src"
            source_dir.mkdir()
            workdir = root / "work"

            sv_path = source_dir / "demo.sv"
            sv_path.write_text("module demo; endmodule\n")

            sby_path = source_dir / "demo.sby"
            sby_path.write_text(
                """[tasks]
prv

[options]
prv: mode prove

[engines]
prv: abc pdr

[script]
read -sv demo.sv
prep -top demo

[files]
demo.sv
"""
            )

            generated = prepare_sby(
                sby_path,
                workdir,
                engine_override="smtbmc",
                selected_tasks=["prv"],
            )
            generated_text = generated.read_text()
            self.assertIn("prv: smtbmc", generated_text)
            self.assertNotIn("prv: abc pdr", generated_text)

    def test_prepare_sby_overrides_inline_task_engines_without_selected_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_dir = root / "src"
            source_dir.mkdir()
            workdir = root / "work"

            sv_path = source_dir / "demo.sv"
            sv_path.write_text("module demo; endmodule\n")

            sby_path = source_dir / "demo.sby"
            sby_path.write_text(
                """[tasks]
prv

[options]
prv: mode prove

[engines]
prv: abc pdr

[script]
read -sv demo.sv
prep -top demo

[files]
demo.sv
"""
            )

            generated = prepare_sby(
                sby_path,
                workdir,
                engine_override="smtbmc",
            )
            generated_text = generated.read_text()
            self.assertIn("prv: smtbmc", generated_text)
            self.assertNotIn("prv: abc pdr", generated_text)

    def test_prepare_sby_rewrites_bind_into_target_instance(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_dir = root / "src"
            source_dir.mkdir()
            workdir = root / "work"

            (source_dir / "demo.sv").write_text(
                """module demo(input logic clk, input logic rst_n, input logic a, input logic b);
endmodule
"""
            )
            (source_dir / "props.sv").write_text(
                """module demo_props(input logic clk, input logic rst_n, input logic a, input logic b);
default clocking @(posedge clk); endclocking
default disable iff (!rst_n);
assert property (a |-> b);
endmodule

bind demo demo_props demo_props_i (.*);
"""
            )
            sby_path = source_dir / "demo.sby"
            sby_path.write_text(
                """[options]
mode bmc
depth 4

[engines]
smtbmc

[script]
read -sv demo.sv
read -sv props.sv
prep -top demo

[files]
demo.sv
props.sv
"""
            )

            generated = prepare_sby(sby_path, workdir)
            generated_text = generated.read_text()

            staged_demo = (workdir / "files" / "demo.sv").read_text()
            staged_props = (workdir / "files" / "props.sv").read_text()
            self.assertIn("read -formal -sv demo.sv", generated_text)
            self.assertIn("read -formal -sv props.sv", generated_text)
            self.assertIn("demo_props demo_props_i", staged_demo)
            self.assertIn(".clk(clk)", staged_demo)
            self.assertIn(".rst_n(rst_n)", staged_demo)
            self.assertIn(".a(a)", staged_demo)
            self.assertIn(".b(b)", staged_demo)
            self.assertIn("// sva_sby: removed bind demo demo_props demo_props_i", staged_props)

    def test_prepare_sby_preserves_unresolved_bind_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_dir = root / "src"
            source_dir.mkdir()
            workdir = root / "work"

            (source_dir / "formal_bind.sv").write_text(
                """module checker_mod(input logic clk, input logic a);
default clocking @(posedge clk); endclocking
assert property (a);
endmodule

bind missing_target checker_mod checker_i (.*);
"""
            )
            sby_path = source_dir / "bind.sby"
            sby_path.write_text(
                """[options]
mode bmc
depth 2

[engines]
smtbmc

[script]
read -formal -sv formal_bind.sv
prep -top checker_mod

[files]
formal_bind.sv
"""
            )

            prepare_sby(sby_path, workdir)
            staged_text = (workdir / "files" / "formal_bind.sv").read_text()
            self.assertIn("bind missing_target checker_mod checker_i (.*);", staged_text)
            self.assertNotIn("// sva_sby: removed bind", staged_text)

    def test_prepare_sby_rewrites_bind_ports_with_unpacked_dimensions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_dir = root / "src"
            source_dir.mkdir()
            workdir = root / "work"

            (source_dir / "demo.sv").write_text(
                """module demo(input logic clk, input logic [1:0] bus [2]);
endmodule
"""
            )
            (source_dir / "props.sv").write_text(
                """module demo_props(input logic clk, input logic [1:0] bus [2]);
default clocking @(posedge clk); endclocking
assert property (bus[0][0]);
endmodule

bind demo demo_props demo_props_i (.*);
"""
            )
            sby_path = source_dir / "demo.sby"
            sby_path.write_text(
                """[options]
mode bmc
depth 2

[engines]
smtbmc

[script]
read -sv demo.sv
read -sv props.sv
prep -top demo

[files]
demo.sv
props.sv
"""
            )

            prepare_sby(sby_path, workdir)
            staged_demo = (workdir / "files" / "demo.sv").read_text()
            self.assertIn(".bus(bus)", staged_demo)
            self.assertNotIn(".[2]([2])", staged_demo)


if __name__ == "__main__":
    unittest.main()
