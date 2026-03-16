#!/usr/bin/env python3
"""Short wrapper entrypoint for the local formal helpers."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
TOOL_BIN = ROOT.parents[1] / "oss-cad-suite" / "bin"


def is_formal_input(arg: str) -> bool:
    return arg.endswith(".sby") or arg.endswith(".sv") or arg.endswith(".v")


def normalize_argv(argv: list[str]) -> list[str]:
    if argv and argv[0] in {"sby", "gui"}:
        return argv
    if any(is_formal_input(arg) for arg in argv):
        return ["sby", *argv]
    return argv


def default_workdir_for_input(input_path: Path, tasks: list[str], top: str | None) -> Path:
    stem = input_path.stem
    suffix = "_".join(tasks) if tasks else (top or stem)
    if suffix == stem:
        return ROOT / "build" / "formal_runs" / stem
    return ROOT / "build" / "formal_runs" / f"{stem}__{suffix}"


def tool_env() -> dict[str, str]:
    env = os.environ.copy()
    if TOOL_BIN.exists():
        current_path = env.get("PATH", "")
        current_parts = current_path.split(os.pathsep) if current_path else []
        if str(TOOL_BIN) not in current_parts:
            env["PATH"] = os.pathsep.join([str(TOOL_BIN), *current_parts]) if current_parts else str(TOOL_BIN)
    return env


def resolve_cli_path(raw_path: Path, base_dir: Path) -> Path:
    expanded = raw_path.expanduser()
    if expanded.is_absolute():
        return expanded.resolve()
    return (base_dir / expanded).resolve()


def run(cmd: list[str]) -> int:
    proc = subprocess.run(cmd, cwd=ROOT, env=tool_env(), check=False)
    return proc.returncode


def find_wave_traces(workdir: Path) -> list[Path]:
    if not workdir.exists():
        return []
    return sorted(path for path in workdir.rglob("trace.vcd") if path.is_file())


def open_wave_traces(workdir: Path) -> None:
    traces = find_wave_traces(workdir)
    if not traces:
        print(f"formal: no trace.vcd found under {workdir}", file=sys.stderr)
        return

    env = tool_env()
    viewer = None
    for candidate in ("gtkwave", "xdg-open", "open"):
        resolved = shutil.which(candidate, path=env.get("PATH"))
        if resolved is not None:
            viewer = resolved
            break

    if viewer is None:
        print("formal: no waveform viewer found on PATH", file=sys.stderr)
        return

    for trace in traces:
        try:
            subprocess.Popen(
                [viewer, str(trace)],
                cwd=ROOT,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print(f"formal: opening {trace}", file=sys.stderr)
        except OSError as exc:
            print(f"formal: failed to open {trace}: {exc}", file=sys.stderr)


def handle_sby(args: argparse.Namespace) -> int:
    caller_cwd = Path.cwd()
    input_path = resolve_cli_path(Path(args.input), caller_cwd)
    tasks = list(args.tasks)
    top = args.top
    if input_path.suffix != ".sby" and top is None:
        top = input_path.stem

    if args.workdir is None:
        workdir = default_workdir_for_input(input_path, tasks, top)
    else:
        workdir = resolve_cli_path(args.workdir, caller_cwd)

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

    result = run(cmd)
    if args.waves:
        open_wave_traces(workdir)
    return result


def handle_gui(args: argparse.Namespace) -> int:
    caller_cwd = Path.cwd().resolve()
    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "gui.py"),
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--project-root",
        str(caller_cwd),
    ]
    if args.open_browser:
        cmd.append("--open-browser")
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
    sby.add_argument("-waves", "--waves", action="store_true", help="Open generated trace.vcd files")
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

    gui = subparsers.add_parser("gui", help="Start the local web GUI")
    gui.add_argument("--host", default="127.0.0.1", help="Bind host; defaults to 127.0.0.1")
    gui.add_argument("--port", type=int, default=8080, help="Bind port; defaults to 8080")
    gui.add_argument(
        "--open-browser",
        action="store_true",
        help="Open the default browser after the server starts",
    )
    gui.set_defaults(handler=handle_gui)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(normalize_argv(sys.argv[1:] if argv is None else argv))
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
