#!/usr/bin/env python3
"""Tests for the short formal wrapper CLI."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import formal


class FormalCliTests(unittest.TestCase):
    def test_normalize_argv_prepends_sby_for_sv_input(self) -> None:
        self.assertEqual(
            formal.normalize_argv(["examples/sva/assert_raw_delay_pass.sv"]),
            ["sby", "examples/sva/assert_raw_delay_pass.sv"],
        )

    def test_normalize_argv_leaves_explicit_sby_usage_unchanged(self) -> None:
        self.assertEqual(
            formal.normalize_argv(["sby", "examples/sva/assert_raw_delay_pass.sv"]),
            ["sby", "examples/sva/assert_raw_delay_pass.sv"],
        )

    def test_normalize_argv_prepends_sby_when_option_precedes_input(self) -> None:
        self.assertEqual(
            formal.normalize_argv(["-waves", "examples/sva/assert_raw_delay_pass.sv"]),
            ["sby", "-waves", "examples/sva/assert_raw_delay_pass.sv"],
        )

    def test_default_workdir_for_sby_task(self) -> None:
        workdir = formal.default_workdir_for_input(Path("props.sby"), ["prv"], None)
        self.assertEqual(workdir, formal.ROOT / "build" / "formal_runs" / "props__prv")

    def test_default_workdir_for_direct_sv_uses_top(self) -> None:
        workdir = formal.default_workdir_for_input(Path("demo.sv"), [], "top_demo")
        self.assertEqual(workdir, formal.ROOT / "build" / "formal_runs" / "demo__top_demo")

    def test_default_workdir_for_direct_sv_uses_stem_when_top_missing(self) -> None:
        workdir = formal.default_workdir_for_input(Path("demo.sv"), [], None)
        self.assertEqual(workdir, formal.ROOT / "build" / "formal_runs" / "demo")

    def test_build_parser_accepts_gui_subcommand(self) -> None:
        args = formal.build_parser().parse_args(["gui", "--port", "8123"])
        self.assertEqual(args.command, "gui")
        self.assertEqual(args.port, 8123)
        self.assertEqual(args.host, "127.0.0.1")

    def test_build_parser_accepts_waves_flag(self) -> None:
        args = formal.build_parser().parse_args(["sby", "-waves", "examples/sva/assert_raw_delay_pass.sby"])
        self.assertTrue(args.waves)

    def test_resolve_cli_path_uses_caller_cwd(self) -> None:
        base_dir = Path("/tmp/example")
        resolved = formal.resolve_cli_path(Path("demo.sv"), base_dir)
        self.assertEqual(resolved, (base_dir / "demo.sv").resolve())

    def test_find_wave_traces_discovers_nested_trace_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workdir = Path(tmpdir)
            (workdir / "run" / "engine_0").mkdir(parents=True)
            (workdir / "run" / "engine_0" / "trace.vcd").write_text("$date\n")
            traces = formal.find_wave_traces(workdir)
            self.assertEqual(traces, [workdir / "run" / "engine_0" / "trace.vcd"])


if __name__ == "__main__":
    unittest.main()
