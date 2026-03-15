#!/usr/bin/env python3
"""Tests for the short formal wrapper CLI."""

from __future__ import annotations

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

    def test_default_workdir_for_sby_task(self) -> None:
        workdir = formal.default_workdir_for_input(Path("props.sby"), ["prv"], None)
        self.assertEqual(workdir, formal.ROOT / "build" / "formal_runs" / "props__prv")

    def test_default_workdir_for_direct_sv_uses_top(self) -> None:
        workdir = formal.default_workdir_for_input(Path("demo.sv"), [], "top_demo")
        self.assertEqual(workdir, formal.ROOT / "build" / "formal_runs" / "demo__top_demo")

    def test_default_workdir_for_direct_sv_uses_stem_when_top_missing(self) -> None:
        workdir = formal.default_workdir_for_input(Path("demo.sv"), [], None)
        self.assertEqual(workdir, formal.ROOT / "build" / "formal_runs" / "demo")


if __name__ == "__main__":
    unittest.main()
