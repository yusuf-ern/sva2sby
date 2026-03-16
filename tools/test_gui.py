#!/usr/bin/env python3
"""Tests for the local web GUI helpers."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import gui


class GuiTests(unittest.TestCase):
    def test_discover_examples_includes_known_example(self) -> None:
        examples = gui.discover_examples()
        self.assertTrue(any(item["path"].endswith("assert_raw_delay_pass.sby") for item in examples))

    def test_parse_run_request_accepts_sby_input_from_project_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "demo.sby").write_text("[options]\nmode bmc\n")
            request = gui.parse_run_request(
                {
                    "project_root": str(project_root),
                    "input_path": "demo.sby",
                    "tasks": ["prove", "cover"],
                    "backend": "sby",
                    "compat": True,
                },
                gui.formal.ROOT,
            )
            self.assertEqual(request.tasks, ["prove", "cover"])
            self.assertTrue(request.compat)
            self.assertEqual(request.input_path, project_root / "demo.sby")
            self.assertEqual(request.project_root, project_root)
            self.assertEqual(request.work_root, project_root / "build" / "formal_runs")

    def test_parse_run_request_rejects_tasks_for_sv_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "demo.sv").write_text("module demo; endmodule\n")
            with self.assertRaisesRegex(ValueError, "tasks are only valid"):
                gui.parse_run_request(
                    {
                        "project_root": str(project_root),
                        "input_path": "demo.sv",
                        "tasks": ["prove"],
                    },
                    gui.formal.ROOT,
                )

    def test_parse_run_request_accepts_custom_work_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "proj"
            work_root = Path(tmpdir) / "custom_runs"
            project_root.mkdir()
            work_root.mkdir()
            (project_root / "demo.sby").write_text("[options]\nmode bmc\n")

            request = gui.parse_run_request(
                {
                    "project_root": str(project_root),
                    "work_root": str(work_root),
                    "input_path": "demo.sby",
                },
                gui.formal.ROOT,
            )
            self.assertEqual(request.work_root, work_root)

    def test_parse_run_request_resolves_relative_work_root_from_project_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "proj"
            project_root.mkdir()
            (project_root / "demo.sby").write_text("[options]\nmode bmc\n")

            request = gui.parse_run_request(
                {
                    "project_root": str(project_root),
                    "work_root": "out/formal",
                    "input_path": "demo.sby",
                },
                gui.formal.ROOT,
            )
            self.assertEqual(request.work_root, project_root / "out" / "formal")

    def test_resolve_browser_directory_uses_parent_for_file_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            nested = root / "proj" / "demo.sby"
            nested.parent.mkdir(parents=True)
            nested.write_text("[options]\nmode bmc\n")
            resolved = gui.resolve_browser_directory(str(nested), root)
            self.assertEqual(resolved, nested.parent)

    def test_resolve_browser_directory_walks_to_existing_parent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            existing = root / "proj"
            existing.mkdir()
            resolved = gui.resolve_browser_directory("proj/missing/deeper", root)
            self.assertEqual(resolved, existing)

    def test_browse_directory_entries_filters_to_supported_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "nested").mkdir()
            (root / "demo.sby").write_text("[options]\nmode bmc\n")
            (root / "helper.sv").write_text("module helper; endmodule\n")
            (root / "notes.txt").write_text("ignore me\n")

            dirs_only = gui.browse_directory_entries(root, include_files=False)
            self.assertEqual(dirs_only, [{"name": "nested", "path": str((root / "nested").resolve()), "kind": "dir"}])

            with_files = gui.browse_directory_entries(root, include_files=True)
            names = [entry["name"] for entry in with_files]
            self.assertIn("nested", names)
            self.assertIn("demo.sby", names)
            self.assertIn("helper.sv", names)
            self.assertNotIn("notes.txt", names)

    def test_build_formal_command_for_direct_sv(self) -> None:
        request = gui.RunRequest(
            project_root=gui.formal.ROOT,
            input_path=(gui.formal.ROOT / "examples" / "sva" / "assert_raw_delay_pass.sv").resolve(),
            tasks=[],
            top="assert_raw_delay_pass",
            mode="prove",
            depth=9,
            backend="auto",
            engine="smtbmc yices",
            compat=False,
            work_root=gui.formal.ROOT / "build" / "formal_runs",
        )
        command, workdir = gui.build_formal_command(request)
        self.assertEqual(command[0], gui.sys.executable)
        self.assertIn("formal.py", command[1])
        self.assertIn("--top", command)
        self.assertIn("--mode", command)
        self.assertIn("--depth", command)
        self.assertIn("--engine", command)
        self.assertTrue(str(workdir).endswith("build/formal_runs/assert_raw_delay_pass"))

    def test_build_formal_command_for_sby_omits_direct_sv_flags(self) -> None:
        request = gui.RunRequest(
            project_root=gui.formal.ROOT,
            input_path=(gui.formal.ROOT / "examples" / "sva" / "assert_raw_delay_pass.sby").resolve(),
            tasks=["prove"],
            top=None,
            mode="bmc",
            depth=5,
            backend="sby",
            engine=None,
            compat=True,
            work_root=gui.formal.ROOT / "build" / "formal_runs",
        )
        command, _ = gui.build_formal_command(request)
        self.assertIn("prove", command)
        self.assertIn("--compat", command)
        self.assertNotIn("--top", command)
        self.assertNotIn("--mode", command)
        self.assertNotIn("--depth", command)

    def test_collect_artifacts_and_resolve_artifact_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workdir = Path(tmpdir)
            (workdir / "run.sby").write_text("[options]\nmode bmc\n")
            (workdir / "lowered.sv").write_text("module demo; endmodule\n")
            (workdir / "run").mkdir()
            (workdir / "run" / "trace.vcd").write_text("$date\n")

            artifacts = gui.collect_artifacts(workdir)
            paths = {entry["path"]: entry for entry in artifacts}
            self.assertIn("run.sby", paths)
            self.assertIn("lowered.sv", paths)
            self.assertIn("run/trace.vcd", paths)
            self.assertTrue(paths["run.sby"]["previewable"])
            self.assertFalse(paths["run/trace.vcd"]["previewable"])

            resolved = gui.resolve_artifact_path(workdir, "run.sby")
            self.assertEqual(resolved, workdir / "run.sby")
            with self.assertRaisesRegex(ValueError, "escapes workdir"):
                gui.resolve_artifact_path(workdir, "../outside.txt")


if __name__ == "__main__":
    unittest.main()
