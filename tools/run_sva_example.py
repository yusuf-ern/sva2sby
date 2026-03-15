#!/usr/bin/env python3
"""Run one SVA example with EBMC, the local sby wrapper, or both."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = ROOT / "examples" / "sva"
OSS_CAD_BIN = Path("/tool/formal_tools/oss-cad-suite/bin")


def available_examples() -> list[str]:
    return sorted(path.stem for path in EXAMPLES_DIR.glob("*.sv"))


def make_env() -> dict[str, str]:
    env = os.environ.copy()
    if OSS_CAD_BIN.is_dir():
        env["PATH"] = str(OSS_CAD_BIN) + os.pathsep + env.get("PATH", "")
    return env


def run_command(cmd: list[str], env: dict[str, str]) -> int:
    print("$ " + " ".join(cmd))
    proc = subprocess.run(cmd, cwd=ROOT, env=env, check=False)
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("example", choices=available_examples(), help="Example name without .sv")
    parser.add_argument("--tool", choices=["ebmc", "sby", "both"], default="both")
    parser.add_argument("--bound", type=int, default=None, help="Override bound")
    args = parser.parse_args()

    default_bounds = {
        "assume_assert_overlap": 3,
        "assume_assert_named_delay": 4,
        "assert_disable_iff_pass": 6,
        "assert_goto_pass": 6,
        "assert_multi_all_pass": 4,
        "assert_multi_one_fail": 4,
        "assert_named_delay_fail": 4,
        "assert_named_delay_pass": 4,
        "assert_nested_sequence_pass": 4,
        "assert_nonconsecutive_pass": 7,
        "assert_raw_delay_fail": 4,
        "assert_raw_delay_pass": 4,
        "cover_disable_iff_hit": 6,
        "cover_named_delay_hit": 4,
        "cover_named_delay_miss": 4,
        "cover_same_cycle_hit": 4,
        "cover_same_cycle_miss": 3,
    }
    bound = args.bound if args.bound is not None else default_bounds.get(args.example, 4)

    env = make_env()
    source = EXAMPLES_DIR / f"{args.example}.sv"
    top = args.example
    rc = 0

    if args.tool in ("ebmc", "both"):
        rc |= run_command(
            ["ebmc", str(source), "--top", top, "--bound", str(bound), "--trace"],
            env,
        )

    if args.tool in ("sby", "both"):
        workdir = ROOT / "build" / "example_runs" / f"{args.example}_sby"
        sby_config = EXAMPLES_DIR / f"{args.example}.sby"
        if sby_config.exists():
            rc |= run_command(
                [
                    sys.executable,
                    str(ROOT / "tools" / "sva_sby.py"),
                    str(sby_config),
                    "--workdir",
                    str(workdir),
                ],
                env,
            )
        else:
            rc |= run_command(
                [
                    sys.executable,
                    str(ROOT / "tools" / "sva_sby.py"),
                    str(source),
                    "--top",
                    top,
                    "--workdir",
                    str(workdir),
                    "--mode",
                    "bmc",
                    "--depth",
                    str(bound),
                ],
                env,
            )

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
