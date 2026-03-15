#!/usr/bin/env python3
"""Short wrapper entrypoint for the local formal helpers."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent


def is_formal_input(arg: str) -> bool:
    return arg.endswith(".sby") or arg.endswith(".sv") or arg.endswith(".v")


def normalize_argv(argv: list[str]) -> list[str]:
    if argv and is_formal_input(argv[0]):
        return ["sby", *argv]
    return argv


def default_workdir_for_input(input_path: Path, tasks: list[str], top: str | None) -> Path:
    stem = input_path.stem
    suffix = "_".join(tasks) if tasks else (top or stem)
    if suffix == stem:
        return ROOT / "build" / "formal_runs" / stem
    return ROOT / "build" / "formal_runs" / f"{stem}__{suffix}"


def run(cmd: list[str]) -> int:
    proc = subprocess.run(cmd, cwd=ROOT, check=False)
    return proc.returncode


def handle_sby(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    tasks = list(args.tasks)
    top = args.top
    if input_path.suffix != ".sby" and top is None:
        top = input_path.stem

    workdir = args.workdir or default_workdir_for_input(input_path, tasks, top)

    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "sva_sby.py"),
        str(input_path),
        *tasks,
        "--workdir",
        str(workdir),
    ]

    if args.compat:
        cmd.append("--strip-verific")
    if args.backend is not None:
        cmd.extend(["--backend", args.backend])
    if args.engine is not None:
        cmd.extend(["--engine", args.engine])
    if input_path.suffix != ".sby":
        cmd.extend(["--top", top or input_path.stem, "--mode", args.mode, "--depth", str(args.depth)])

    return run(cmd)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    sby = subparsers.add_parser("sby", help="Run the local SVA->sby wrapper with short defaults")
    sby.add_argument("input", help="Input .sby, .sv, or .v file")
    sby.add_argument("tasks", nargs="*", help="Optional task names for .sby input")
    sby.add_argument("--top", help="Top module for direct .sv/.v input; defaults to file stem")
    sby.add_argument("--workdir", type=Path, help="Run directory; defaults to build/formal_runs/<name>")
    sby.add_argument("--mode", choices=["bmc", "prove", "cover"], default="bmc")
    sby.add_argument("--depth", type=int, default=5)
    sby.add_argument(
        "--backend",
        choices=["auto", "sby", "ebmc"],
        default="auto",
        help="Backend selection; auto uses ebmc for full-SVA operators and sby otherwise",
    )
    sby.add_argument(
        "--engine",
        help="Engine override, for example 'smtbmc yices' or 'smtbmc'",
    )
    sby.add_argument(
        "--compat",
        action="store_true",
        help="Enable wrapper compatibility mode for some Verific-gated .sby examples",
    )
    sby.set_defaults(handler=handle_sby)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(normalize_argv(sys.argv[1:] if argv is None else argv))
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
