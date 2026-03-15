#!/usr/bin/env python3
"""Compare EBMC and the local SVA lowering flow on a matrix of cases."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_WORKDIR = SCRIPT_DIR.parent / "build" / "compare_ebmc_sby"
OSS_CAD_BIN = Path("/tool/formal_tools/oss-cad-suite/bin")


@dataclass(frozen=True)
class Case:
    name: str
    mode: str
    bound: int
    expectation: str
    source: str


RESULT_RE = re.compile(r"^\[(?P<id>[^\]]+)\]\s+(?P<body>.*):\s+(?P<status>.+)$", re.MULTILINE)


def make_env() -> dict[str, str]:
    env = os.environ.copy()
    if OSS_CAD_BIN.is_dir():
        env["PATH"] = str(OSS_CAD_BIN) + os.pathsep + env.get("PATH", "")
    return env


def run(cmd: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def classify_ebmc_property(match: dict[str, str]) -> str:
    prop_id = match["id"]
    if ".assume." in prop_id or match["status"].startswith("ASSUMED"):
        return "assume"
    if ".cover." in prop_id or match["body"].startswith("cover "):
        return "cover"
    return "assert"


def parse_ebmc(expectation: str, text: str) -> str:
    matches = [match.groupdict() for match in RESULT_RE.finditer(text)]
    if not matches:
        return "error"

    if expectation == "assert":
        assert_statuses = [
            match["status"]
            for match in matches
            if classify_ebmc_property(match) == "assert"
        ]
        if not assert_statuses:
            return "error"
        if any(status.startswith("REFUTED") for status in assert_statuses):
            return "fail"
        if all(status.startswith("PROVED") for status in assert_statuses):
            return "pass"
        return "error"

    if expectation == "assume_assert":
        saw_assume = any(classify_ebmc_property(match) == "assume" for match in matches)
        assert_statuses = [
            match["status"]
            for match in matches
            if classify_ebmc_property(match) == "assert"
        ]
        if not assert_statuses:
            return "error"
        if any(status.startswith("REFUTED") for status in assert_statuses):
            return "fail"
        if saw_assume and all(status.startswith("PROVED") for status in assert_statuses):
            return "pass"
        return "error"

    if expectation == "cover":
        for match in matches:
            if classify_ebmc_property(match) == "cover":
                status = match["status"]
                if status.startswith("PROVED"):
                    return "hit"
                if status.startswith("REFUTED"):
                    return "miss"
        return "error"

    if expectation == "unsupported":
        return "supported"

    return "error"


def parse_sby(expectation: str, proc: subprocess.CompletedProcess[str]) -> str:
    text = proc.stdout + proc.stderr

    if "No supported property statements were found" in text:
        return "unsupported"
    if "multi-cycle bare sequence" in text:
        return "unsupported"

    if expectation in ("assert", "assume_assert"):
        if proc.returncode == 0:
            return "pass"
        if "Assert failed" in text or "BMC failed!" in text:
            return "fail"
        return "error"

    if expectation == "cover":
        if proc.returncode == 0:
            return "hit"
        if "Unreached cover statement" in text:
            return "miss"
        return "error"

    if expectation == "unsupported":
        return "unsupported" if proc.returncode != 0 else "supported"

    return "error"


def compare_status(expectation: str, ebmc_status: str, sby_status: str) -> str:
    if expectation == "unsupported":
        return "expected-gap" if sby_status == "unsupported" else "unexpected-support"
    if ebmc_status == sby_status:
        return "match"
    return "mismatch"


def write_case(case: Case, workdir: Path) -> Path:
    path = workdir / "cases" / f"{case.name}.sv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(case.source)
    return path


def run_case(case: Case, workdir: Path, env: dict[str, str]) -> tuple[str, str, str]:
    source_path = write_case(case, workdir)

    ebmc_proc = run(
        ["ebmc", str(source_path), "--top", case.name, "--bound", str(case.bound), "--trace"],
        cwd=workdir,
        env=env,
    )
    ebmc_status = parse_ebmc(case.expectation, ebmc_proc.stdout + ebmc_proc.stderr)

    sby_workdir = workdir / "sby" / case.name
    sby_proc = run(
        [
            sys.executable,
            str(SCRIPT_DIR / "sva_sby.py"),
            str(source_path),
            "--top",
            case.name,
            "--workdir",
            str(sby_workdir),
            "--mode",
            case.mode,
            "--depth",
            str(case.bound),
        ],
        cwd=SCRIPT_DIR.parent,
        env=env,
    )
    sby_status = parse_sby(case.expectation, sby_proc)
    verdict = compare_status(case.expectation, ebmc_status, sby_status)

    logs_dir = workdir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / f"{case.name}.ebmc.log").write_text(ebmc_proc.stdout + ebmc_proc.stderr)
    (logs_dir / f"{case.name}.sby.log").write_text(sby_proc.stdout + sby_proc.stderr)

    return ebmc_status, sby_status, verdict


def build_cases() -> list[Case]:
    return [
        Case(
            name="assert_same_cycle_pass",
            mode="bmc",
            bound=2,
            expectation="assert",
            source="""module assert_same_cycle_pass(input logic clk);
\tlogic a;
\tinitial a = 1'b1;
\talways @(posedge clk)
\t\ta <= 1'b1;
\tproperty p;
\t\t@(posedge clk) a;
\tendproperty
\tassert property (p);
endmodule
""",
        ),
        Case(
            name="assert_same_cycle_fail",
            mode="bmc",
            bound=2,
            expectation="assert",
            source="""module assert_same_cycle_fail(input logic clk);
\tlogic a;
\tinitial a = 1'b0;
\talways @(posedge clk)
\t\ta <= 1'b0;
\tproperty p;
\t\t@(posedge clk) a;
\tendproperty
\tassert property (p);
endmodule
""",
        ),
        Case(
            name="assert_overlap_pass",
            mode="bmc",
            bound=3,
            expectation="assert",
            source="""module assert_overlap_pass(input logic clk);
\tlogic [1:0] cnt;
\twire req;
\twire mid;
\tinitial cnt = 2'b00;
\talways @(posedge clk)
\t\tcnt <= cnt + 2'b01;
\tassign req = (cnt == 2'b00);
\tassign mid = (cnt == 2'b00);
\tproperty p;
\t\t@(posedge clk) req |-> mid;
\tendproperty
\tassert property (p);
endmodule
""",
        ),
        Case(
            name="assert_overlap_fail",
            mode="bmc",
            bound=3,
            expectation="assert",
            source="""module assert_overlap_fail(input logic clk);
\tlogic [1:0] cnt;
\twire req;
\twire mid;
\tinitial cnt = 2'b00;
\talways @(posedge clk)
\t\tcnt <= cnt + 2'b01;
\tassign req = (cnt == 2'b00);
\tassign mid = (cnt == 2'b01);
\tproperty p;
\t\t@(posedge clk) req |-> mid;
\tendproperty
\tassert property (p);
endmodule
""",
        ),
        Case(
            name="assert_nonoverlap_pass",
            mode="bmc",
            bound=3,
            expectation="assert",
            source="""module assert_nonoverlap_pass(input logic clk);
\tlogic [1:0] cnt;
\twire req;
\twire done;
\tinitial cnt = 2'b00;
\talways @(posedge clk)
\t\tcnt <= cnt + 2'b01;
\tassign req = (cnt == 2'b00);
\tassign done = (cnt == 2'b01);
\tproperty p;
\t\t@(posedge clk) req |=> done;
\tendproperty
\tassert property (p);
endmodule
""",
        ),
        Case(
            name="assert_nonoverlap_fail",
            mode="bmc",
            bound=3,
            expectation="assert",
            source="""module assert_nonoverlap_fail(input logic clk);
\tlogic [1:0] cnt;
\twire req;
\twire done;
\tinitial cnt = 2'b00;
\talways @(posedge clk)
\t\tcnt <= cnt + 2'b01;
\tassign req = (cnt == 2'b00);
\tassign done = (cnt == 2'b10);
\tproperty p;
\t\t@(posedge clk) req |=> done;
\tendproperty
\tassert property (p);
endmodule
""",
        ),
        Case(
            name="assert_raw_delay_pass",
            mode="bmc",
            bound=4,
            expectation="assert",
            source="""module assert_raw_delay_pass(input logic clk);
\tlogic [1:0] cnt;
\twire req;
\twire mid;
\twire done;
\tinitial cnt = 2'b00;
\talways @(posedge clk)
\t\tcnt <= cnt + 2'b01;
\tassign req = (cnt == 2'b00);
\tassign mid = (cnt == 2'b01);
\tassign done = (cnt == 2'b10);
\tproperty p;
\t\t@(posedge clk) req |=> mid ##1 done;
\tendproperty
\tassert property (p);
endmodule
""",
        ),
        Case(
            name="assert_raw_delay_fail",
            mode="bmc",
            bound=4,
            expectation="assert",
            source="""module assert_raw_delay_fail(input logic clk);
\tlogic [1:0] cnt;
\twire req;
\twire mid;
\twire done;
\tinitial cnt = 2'b00;
\talways @(posedge clk)
\t\tcnt <= cnt + 2'b01;
\tassign req = (cnt == 2'b00);
\tassign mid = (cnt == 2'b01);
\tassign done = (cnt == 2'b10);
\tproperty p;
\t\t@(posedge clk) req |=> done ##1 mid;
\tendproperty
\tassert property (p);
endmodule
""",
        ),
        Case(
            name="assert_named_delay_pass",
            mode="bmc",
            bound=4,
            expectation="assert",
            source="""module assert_named_delay_pass(input logic clk);
\tlogic [1:0] cnt;
\twire req;
\twire mid;
\twire done;
\tinitial cnt = 2'b00;
\talways @(posedge clk)
\t\tcnt <= cnt + 2'b01;
\tassign req = (cnt == 2'b00);
\tassign mid = (cnt == 2'b01);
\tassign done = (cnt == 2'b10);
\tsequence s_mid_done;
\t\tmid ##1 done;
\tendsequence
\tproperty p;
\t\t@(posedge clk) req |=> s_mid_done;
\tendproperty
\tassert property (p);
endmodule
""",
        ),
        Case(
            name="assert_named_delay_fail",
            mode="bmc",
            bound=4,
            expectation="assert",
            source="""module assert_named_delay_fail(input logic clk);
\tlogic [1:0] cnt;
\twire req;
\twire mid;
\twire done;
\tinitial cnt = 2'b00;
\talways @(posedge clk)
\t\tcnt <= cnt + 2'b01;
\tassign req = (cnt == 2'b00);
\tassign mid = (cnt == 2'b01);
\tassign done = (cnt == 2'b10);
\tsequence s_done_mid;
\t\tdone ##1 mid;
\tendsequence
\tproperty p;
\t\t@(posedge clk) req |=> s_done_mid;
\tendproperty
\tassert property (p);
endmodule
""",
        ),
        Case(
            name="assert_nested_sequence_pass",
            mode="bmc",
            bound=4,
            expectation="assert",
            source="""module assert_nested_sequence_pass(input logic clk);
\tlogic [1:0] cnt;
\twire req;
\twire mid;
\twire done;
\tinitial cnt = 2'b00;
\talways @(posedge clk)
\t\tcnt <= cnt + 2'b01;
\tassign req = (cnt == 2'b00);
\tassign mid = (cnt == 2'b01);
\tassign done = (cnt == 2'b10);
\tsequence s_done;
\t\tdone;
\tendsequence
\tsequence s_mid_done;
\t\tmid ##1 s_done;
\tendsequence
\tproperty p;
\t\t@(posedge clk) req |=> s_mid_done;
\tendproperty
\tassert property (p);
endmodule
""",
        ),
        Case(
            name="assert_disable_iff_pass",
            mode="bmc",
            bound=6,
            expectation="assert",
            source="""module assert_disable_iff_pass(input logic clk);
\tlogic rst_n;
\tlogic [2:0] cnt;
\twire req;
\twire mid;
\twire done;
\tinitial begin
\t\trst_n = 1'b0;
\t\tcnt = 3'b000;
\tend
\talways @(posedge clk) begin
\t\trst_n <= 1'b1;
\t\tcnt <= cnt + 3'b001;
\tend
\tassign req = (cnt == 3'b001);
\tassign mid = (cnt == 3'b010);
\tassign done = (cnt == 3'b011);
\tproperty p;
\t\t@(posedge clk) disable iff (!rst_n) req |=> mid ##1 done;
\tendproperty
\tassert property (p);
endmodule
""",
        ),
        Case(
            name="assert_multi_all_pass",
            mode="bmc",
            bound=4,
            expectation="assert",
            source="""module assert_multi_all_pass(input logic clk);
\tlogic [1:0] cnt;
\twire req;
\twire mid;
\twire done;
\tinitial cnt = 2'b00;
\talways @(posedge clk)
\t\tcnt <= cnt + 2'b01;
\tassign req = (cnt == 2'b00);
\tassign mid = (cnt == 2'b01);
\tassign done = (cnt == 2'b10);
\tproperty p0;
\t\t@(posedge clk) req |=> mid;
\tendproperty
\tproperty p1;
\t\t@(posedge clk) req |=> mid ##1 done;
\tendproperty
\tassert property (p0);
\tassert property (p1);
endmodule
""",
        ),
        Case(
            name="assert_multi_one_fail",
            mode="bmc",
            bound=4,
            expectation="assert",
            source="""module assert_multi_one_fail(input logic clk);
\tlogic [1:0] cnt;
\twire req;
\twire mid;
\twire done;
\tinitial cnt = 2'b00;
\talways @(posedge clk)
\t\tcnt <= cnt + 2'b01;
\tassign req = (cnt == 2'b00);
\tassign mid = (cnt == 2'b01);
\tassign done = (cnt == 2'b10);
\tproperty p0;
\t\t@(posedge clk) req |=> mid;
\tendproperty
\tproperty p1;
\t\t@(posedge clk) req |=> done ##1 mid;
\tendproperty
\tassert property (p0);
\tassert property (p1);
endmodule
""",
        ),
        Case(
            name="assume_assert_overlap",
            mode="bmc",
            bound=3,
            expectation="assume_assert",
            source="""module assume_assert_overlap(input logic clk, input logic req, input logic ack);
\tproperty p_env;
\t\t@(posedge clk) req |-> ack;
\tendproperty
\tproperty p_safe;
\t\t@(posedge clk) req |-> ack;
\tendproperty
\tassume property (p_env);
\tassert property (p_safe);
endmodule
""",
        ),
        Case(
            name="assume_assert_named_delay",
            mode="bmc",
            bound=4,
            expectation="assume_assert",
            source="""module assume_assert_named_delay(
\tinput logic clk,
\tinput logic req,
\tinput logic mid,
\tinput logic done
);
\tsequence s_mid_done;
\t\tmid ##1 done;
\tendsequence
\tproperty p_env;
\t\t@(posedge clk) req |=> s_mid_done;
\tendproperty
\tproperty p_safe;
\t\t@(posedge clk) req |=> s_mid_done;
\tendproperty
\tassume property (p_env);
\tassert property (p_safe);
endmodule
""",
        ),
        Case(
            name="cover_same_cycle_hit",
            mode="cover",
            bound=4,
            expectation="cover",
            source="""module cover_same_cycle_hit(input logic clk);
\tlogic [1:0] cnt;
\twire hit;
\tinitial cnt = 2'b00;
\talways @(posedge clk)
\t\tcnt <= cnt + 2'b01;
\tassign hit = (cnt == 2'b10);
\tproperty p_cov;
\t\t@(posedge clk) hit;
\tendproperty
\tcover property (p_cov);
endmodule
""",
        ),
        Case(
            name="cover_same_cycle_miss",
            mode="cover",
            bound=3,
            expectation="cover",
            source="""module cover_same_cycle_miss(input logic clk);
\tlogic hit;
\tinitial hit = 1'b0;
\talways @(posedge clk)
\t\thit <= 1'b0;
\tproperty p_cov;
\t\t@(posedge clk) hit;
\tendproperty
\tcover property (p_cov);
endmodule
""",
        ),
        Case(
            name="cover_named_delay_hit",
            mode="cover",
            bound=4,
            expectation="cover",
            source="""module cover_named_delay_hit(input logic clk);
\tlogic [1:0] cnt;
\twire req;
\twire done;
\tinitial cnt = 2'b00;
\talways @(posedge clk)
\t\tcnt <= cnt + 2'b01;
\tassign req = (cnt == 2'b00);
\tassign done = (cnt == 2'b01);
\tsequence s_req_done;
\t\treq ##1 done;
\tendsequence
\tproperty p_cov;
\t\t@(posedge clk) s_req_done;
\tendproperty
\tcover property (p_cov);
endmodule
""",
        ),
        Case(
            name="cover_named_delay_miss",
            mode="cover",
            bound=4,
            expectation="cover",
            source="""module cover_named_delay_miss(input logic clk);
\tlogic [1:0] cnt;
\twire req;
\twire never_done;
\tinitial cnt = 2'b00;
\talways @(posedge clk)
\t\tcnt <= cnt + 2'b01;
\tassign req = (cnt == 2'b00);
\tassign never_done = 1'b0;
\tsequence s_req_done;
\t\treq ##1 never_done;
\tendsequence
\tproperty p_cov;
\t\t@(posedge clk) s_req_done;
\tendproperty
\tcover property (p_cov);
endmodule
""",
        ),
        Case(
            name="cover_disable_iff_hit",
            mode="cover",
            bound=6,
            expectation="cover",
            source="""module cover_disable_iff_hit(input logic clk);
\tlogic rst_n;
\tlogic [2:0] cnt;
\twire req;
\twire done;
\tinitial begin
\t\trst_n = 1'b0;
\t\tcnt = 3'b000;
\tend
\talways @(posedge clk) begin
\t\trst_n <= 1'b1;
\t\tcnt <= cnt + 3'b001;
\tend
\tassign req = (cnt == 3'b001);
\tassign done = (cnt == 3'b010);
\tproperty p_cov;
\t\t@(posedge clk) disable iff (!rst_n) req ##1 done;
\tendproperty
\tcover property (p_cov);
endmodule
""",
        ),
        Case(
            name="inline_assert_ebmc_only",
            mode="bmc",
            bound=2,
            expectation="assert",
            source="""module inline_assert_ebmc_only(input logic clk);
\tlogic a;
\tinitial a = 1'b1;
\talways @(posedge clk)
\t\ta <= 1'b1;
\tassert property (@(posedge clk) a);
endmodule
""",
        ),
        Case(
            name="multicycle_bare_assert_ebmc_only",
            mode="bmc",
            bound=3,
            expectation="unsupported",
            source="""module multicycle_bare_assert_ebmc_only(input logic clk);
\tlogic [1:0] cnt;
\twire req;
\twire done;
\tinitial cnt = 2'b00;
\talways @(posedge clk)
\t\tcnt <= cnt + 2'b01;
\tassign req = (cnt == 2'b00);
\tassign done = (cnt == 2'b01);
\tproperty p;
\t\t@(posedge clk) req ##1 done;
\tendproperty
\tassert property (p);
endmodule
""",
        ),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workdir", type=Path, default=DEFAULT_WORKDIR)
    args = parser.parse_args()

    env = make_env()
    if shutil.which("ebmc", path=env.get("PATH")) is None:
        print("ebmc not found on PATH", file=sys.stderr)
        return 2
    if shutil.which("sby", path=env.get("PATH")) is None:
        print("sby not found on PATH", file=sys.stderr)
        return 2

    args.workdir.mkdir(parents=True, exist_ok=True)

    rows: list[tuple[str, str, str, str]] = []
    for case in build_cases():
        ebmc_status, sby_status, verdict = run_case(case, args.workdir, env)
        rows.append((case.name, ebmc_status, sby_status, verdict))

    name_width = max(len("case"), max(len(row[0]) for row in rows))
    ebmc_width = max(len("ebmc"), max(len(row[1]) for row in rows))
    sby_width = max(len("sby"), max(len(row[2]) for row in rows))
    verdict_width = max(len("verdict"), max(len(row[3]) for row in rows))

    header = (
        f"{'case'.ljust(name_width)}  "
        f"{'ebmc'.ljust(ebmc_width)}  "
        f"{'sby'.ljust(sby_width)}  "
        f"{'verdict'.ljust(verdict_width)}"
    )
    print(header)
    print("-" * len(header))
    for row in rows:
        print(
            f"{row[0].ljust(name_width)}  "
            f"{row[1].ljust(ebmc_width)}  "
            f"{row[2].ljust(sby_width)}  "
            f"{row[3].ljust(verdict_width)}"
        )

    mismatches = [row for row in rows if row[3] == "mismatch"]
    unexpected = [row for row in rows if row[3] == "unexpected-support"]
    print()
    print(f"logs: {args.workdir / 'logs'}")
    if mismatches or unexpected:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
