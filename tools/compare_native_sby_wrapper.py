#!/usr/bin/env python3
"""Compare native SymbiYosys results against the local wrapper on upstream examples."""

from __future__ import annotations

import argparse
import concurrent.futures
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_EXAMPLES = Path("/tool/formal_tools/oss-cad-suite/examples")
DEFAULT_WORKDIR = REPO_ROOT / "build" / "compare_native_sby_wrapper"
OSS_CAD_BIN = Path("/tool/formal_tools/oss-cad-suite/bin")


DONE_RE = re.compile(r"DONE \((?P<status>[A-Z]+), rc=(?P<rc>\d+)\)")


@dataclass(frozen=True)
class Job:
    sby_path: Path
    task: str | None

    @property
    def key(self) -> str:
        rel = self.sby_path.relative_to(DEFAULT_EXAMPLES)
        stem = rel.with_suffix("").as_posix().replace("/", "__")
        return stem if self.task is None else f"{stem}__{self.task}"

    @property
    def label(self) -> str:
        rel = self.sby_path.relative_to(DEFAULT_EXAMPLES).as_posix()
        return rel if self.task is None else f"{rel}:{self.task}"


@dataclass(frozen=True)
class Outcome:
    status: str
    detail: str
    rc: int | None
    timed_out: bool = False


def make_env() -> dict[str, str]:
    env = os.environ.copy()
    if OSS_CAD_BIN.is_dir():
        env["PATH"] = str(OSS_CAD_BIN) + os.pathsep + env.get("PATH", "")
    return env


def parse_tasks(sby_path: Path) -> list[str | None]:
    text = sby_path.read_text()
    in_tasks = False
    tasks: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("[") and line.endswith("]"):
            in_tasks = line.lower() == "[tasks]"
            continue
        if not in_tasks or not line or line.startswith("#") or line == "--":
            continue
        task = line.split()[0]
        if task not in tasks:
            tasks.append(task)
    return tasks or [None]


def classify_output(text: str, rc: int | None, timed_out: bool) -> Outcome:
    if timed_out:
        return Outcome("timeout", "timeout", rc, timed_out=True)

    lowered = text.lower()
    if "without verific support" in lowered:
        return Outcome("env-missing", "verific", rc)
    if "vhd2vl" in lowered and "not found" in lowered:
        return Outcome("env-missing", "vhd2vl", rc)
    if "mcy" in lowered and "not found" in lowered:
        return Outcome("env-missing", "mcy", rc)
    if "eqy" in lowered and "not found" in lowered:
        return Outcome("env-missing", "eqy", rc)
    if "yosys-abc" in lowered and "not found" in lowered:
        return Outcome("env-missing", "yosys-abc", rc)

    done_matches = list(DONE_RE.finditer(text))
    if done_matches:
        match = done_matches[-1]
        return Outcome(match.group("status").lower(), match.group("status"), int(match.group("rc")))

    if "no supported property statements were found" in lowered:
        return Outcome("wrapper-gap", "no-supported-property", rc)
    if "multi-cycle bare sequence" in lowered:
        return Outcome("wrapper-gap", "multicycle-bare-sequence", rc)
    return Outcome("error", "error", rc)


def run_command(
    cmd: list[str],
    cwd: Path,
    env: dict[str, str],
    timeout: int,
) -> tuple[str, int | None, bool]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
        return proc.stdout + proc.stderr, proc.returncode, False
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        output = stdout + stderr
        return output, None, True


def compare(native: Outcome, wrapper: Outcome) -> str:
    if native.status == wrapper.status and native.detail == wrapper.detail:
        return "match"
    if native.status == "env-missing" and wrapper.status in {"pass", "fail"}:
        return "wrapper-improves"
    if native.status in {"pass", "fail", "error", "timeout"} and wrapper.status == "wrapper-gap":
        return "wrapper-gap"
    if native.status == "env-missing" and wrapper.status == "env-missing":
        return "env-match"
    return "mismatch"


def write_log(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def run_job(job: Job, workdir: Path, env: dict[str, str], timeout: int) -> tuple[Outcome, Outcome, str]:
    native_dir = workdir / "native" / job.key
    wrapper_dir = workdir / "wrapper" / job.key
    logs_dir = workdir / "logs"

    task_args = [] if job.task is None else [job.task]

    native_cmd = [
        str(OSS_CAD_BIN / "sby"),
        "-f",
        job.sby_path.name,
        *task_args,
        "-d",
        str(native_dir),
    ]
    wrapper_cmd = [
        sys.executable,
        str(SCRIPT_DIR / "sva_sby.py"),
        str(job.sby_path),
        *task_args,
        "--workdir",
        str(wrapper_dir),
    ]
    wrapper_compat_cmd = [
        sys.executable,
        str(SCRIPT_DIR / "sva_sby.py"),
        str(job.sby_path),
        *task_args,
        "--strip-verific",
        "--workdir",
        str(wrapper_dir),
    ]

    native_output, native_rc, native_timed_out = run_command(
        native_cmd,
        job.sby_path.parent,
        env,
        timeout,
    )
    wrapper_output, wrapper_rc, wrapper_timed_out = run_command(
        wrapper_cmd,
        REPO_ROOT,
        env,
        timeout,
    )

    native = classify_output(native_output, native_rc, native_timed_out)
    wrapper = classify_output(wrapper_output, wrapper_rc, wrapper_timed_out)

    if (
        native.status == "env-missing"
        and native.detail == "verific"
        and wrapper.status == "env-missing"
        and wrapper.detail == "verific"
    ):
        compat_output, compat_rc, compat_timed_out = run_command(
            wrapper_compat_cmd,
            REPO_ROOT,
            env,
            timeout,
        )
        compat = classify_output(compat_output, compat_rc, compat_timed_out)
        if compat.status in {"pass", "fail"}:
            wrapper_output = compat_output
            wrapper = compat

    verdict = compare(native, wrapper)

    write_log(logs_dir / f"{job.key}.native.log", native_output)
    write_log(logs_dir / f"{job.key}.wrapper.log", wrapper_output)

    return native, wrapper, verdict


def discover_jobs(examples_root: Path) -> list[Job]:
    jobs: list[Job] = []
    for sby_path in sorted(examples_root.rglob("*.sby")):
        for task in parse_tasks(sby_path):
            jobs.append(Job(sby_path, task))
    return jobs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--examples-root", type=Path, default=DEFAULT_EXAMPLES)
    parser.add_argument("--workdir", type=Path, default=DEFAULT_WORKDIR)
    parser.add_argument("--timeout", type=int, default=30, help="Per-run timeout in seconds")
    parser.add_argument("--jobs", type=int, default=4, help="Number of concurrent jobs")
    args = parser.parse_args()
    args.examples_root = args.examples_root.resolve()
    args.workdir = args.workdir.resolve()

    env = make_env()
    args.workdir.mkdir(parents=True, exist_ok=True)

    jobs = discover_jobs(args.examples_root)
    if not jobs:
        print("No .sby jobs found.", file=sys.stderr)
        return 2

    results: list[tuple[Job, Outcome, Outcome, str]] = []
    total = len(jobs)
    completed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.jobs)) as executor:
        future_to_job = {
            executor.submit(run_job, job, args.workdir, env, args.timeout): job for job in jobs
        }
        for future in concurrent.futures.as_completed(future_to_job):
            job = future_to_job[future]
            native, wrapper, verdict = future.result()
            results.append((job, native, wrapper, verdict))
            completed += 1
            print(
                f"[{completed}/{total}] {job.label} native={native.status}:{native.detail} "
                f"wrapper={wrapper.status}:{wrapper.detail} verdict={verdict}",
                flush=True,
            )

    results.sort(key=lambda item: item[0].label)

    label_width = max(len(job.label) for job, _, _, _ in results)
    print(f"{'job'.ljust(label_width)}  native       wrapper      verdict")
    print(f"{'-' * label_width}  -----------  -----------  ---------------")
    for job, native, wrapper, verdict in results:
        native_text = f"{native.status}:{native.detail}"
        wrapper_text = f"{wrapper.status}:{wrapper.detail}"
        print(f"{job.label.ljust(label_width)}  {native_text.ljust(11)}  {wrapper_text.ljust(11)}  {verdict}")

    summary: dict[str, int] = {}
    for _, _, _, verdict in results:
        summary[verdict] = summary.get(verdict, 0) + 1

    print("\nSummary:")
    for key in sorted(summary):
        print(f"{key}: {summary[key]}")

    return 0 if summary.get("mismatch", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
