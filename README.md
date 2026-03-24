# enhanced-oss-cad

Concurrent SVA experimentation on top of the open-source formal stack.

This repository is a focused prototype for one problem: making more
SystemVerilog Assertion code usable in an `sby`-driven flow without requiring a
commercial frontend. It does that with a local SVA lowering pass, a wrapper
that can stage existing `.sby` projects, and a curated example set that checks
the supported subset against real formal engines.

## Why This Exists

Open-source formal flows are strong at RTL verification, but concurrent SVA
support is still uneven. In practice that means a user often has one of two
bad choices:

- rewrite assertions by hand into lower-level formal logic
- switch to a different frontend or engine for the whole project

This repo explores a middle path:

- keep the normal `sby` workflow where possible
- lower a bounded, explicit SVA subset into ordinary formal RTL
- preserve existing `.sby` files instead of inventing a new user interface
- fall back to `ebmc` only when the local lowering would be incorrect

## What The Repo Provides

- `formal`
  The main CLI. This is the entrypoint intended for day-to-day use.
- `tools/sva_lower.py`
  Source-to-source lowering from a supported SVA subset into Yosys-compatible
  formal RTL under `` `ifdef FORMAL ``.
- `tools/sva_sby.py`
  Wrapper that accepts either raw `.sv` input or an existing `.sby` file,
  stages the sources, lowers what it can, and runs the formal job.
- `tools/gui.py`
  Local web GUI that launches the same wrapper, streams logs, and surfaces
  generated run artifacts under `build/formal_runs/`.
- `examples/sva/`
  Runnable passing and failing examples for the supported feature set.
- `.github/workflows/smoke.yml`
  CI smoke test on push and pull request.
- `.githooks/pre-push`
  Local push gate that runs the same smoke test before `git push`.

## Design Approach

The repo is built around a simple idea:

1. Parse only the SVA subset we can model confidently.
2. Lower that subset into explicit monitor logic plus immediate
   `assert(...)`, `assume(...)`, and `cover(...)`.
3. Keep the outer user workflow shaped like normal SymbiYosys.
4. Be explicit about boundaries instead of pretending to support full SVA.

That means this project is not trying to be a full SystemVerilog parser. It is
trying to be a practical bridge between common assertion styles and the current
open-source toolchain.

## Supported Today

The local lowering path currently covers a bounded subset including:

| Feature | Status | Notes |
| --- | --- | --- |
| Named `sequence` / `property` | Supported | Single-clock subset |
| `|->` and `|=>` | Supported | Core implication forms |
| Fixed delays `##N` | Supported | Direct lowering |
| Simple ranged delays `##[M:N]` | Supported | Bounded |
| Bounded repetition `[*M:N]` | Supported | Includes simple chained tails |
| Goto repetition `[->N]` | Supported | Depth-bounded lowering |
| Nonconsecutive repetition `[=N]` | Supported | Depth-bounded lowering |
| `$rose/$fell/$stable/$changed` inside property terms | Supported | Lowered with sampled helper state on the pure `sby` path |
| `assert property` / `assume property` / `cover property` | Supported | Named and anonymous forms, including multiline action statements |
| `default clocking` | Supported | Single module-level default clocking in one-line or multiline form |
| `disable iff` | Supported | Inline or single module-level default `disable iff` |
| `throughout` | Supported | Single-cycle guard over an exact-delay rhs sequence on the pure `sby` path |
| Existing `.sby` files | Supported | Wrapper stages and rewrites sources |
| Optional `ebmc` backend | Supported | For operators outside the safe local subset |

The important qualifier is boundedness. Several operators are modeled with an
explicit depth bound rather than a mathematically unbounded automaton.

## How It Works

For direct `.sv` input:

1. `formal` forwards to `tools/sva_sby.py`
2. `sva_sby.py` lowers the supported SVA subset into plain formal RTL
3. the wrapper generates a working directory under `build/formal_runs/`
4. `sby` runs on the generated design

For `.sby` input:

1. the wrapper reads the original `.sby`
2. source files in `[files]` and inline `[file ...]` blocks are staged into a generated workdir
3. supported SVA is lowered in those staged copies
4. the generated `.sby` keeps the original task/options structure and runs through `sby`

For unsupported operators:

- `--backend auto` can route the job to `ebmc`
- the front-end shape remains the same, but the semantics come from `ebmc`

## Quick Start

### Prerequisites

- `python3`
- `sby` on `PATH`
- `ebmc` on `PATH` if you want the optional fallback path

### Run The Wrapper

```bash
./formal examples/sva/assert_raw_delay_pass.sby
./formal examples/sva/assert_raw_delay_pass.sv
./formal examples/sva/assert_goto_pass.sby prove
./formal examples/sva/assert_nonconsecutive_fail.sby bmc
./formal -waves examples/sva/assert_raw_delay_fail.sby
```

When given a `.sv` or `.sby` path directly, `formal` automatically routes to
the wrapper and creates a default workdir under `build/formal_runs/`.

`-waves` / `--waves` scans the generated workdir after the run and opens any
`trace.vcd` files with `gtkwave` when it is available on `PATH`.

### Run The GUI

```bash
./formal gui --port 8080
```

Then open `http://127.0.0.1:8080` in a browser. The GUI can launch custom
`.sv` / `.sby` inputs from any local project root, browse project/work/input
paths directly from the form, tail live logs, and preview generated text
artifacts from each run directory. Relative paths in the form resolve from the
selected project root, and generated runs default to
`<project-root>/build/formal_runs/`.

### Install On PATH

The wrapper now prepends the sibling OSS-CAD tool suite bin directory when it
runs, so bundled tools like `sby`, `ebmc`, and `gtkwave` are found even when
your shell `PATH` is minimal.

To expose the wrapper itself as a command from anywhere, install the repo entry
point into the suite bin directory:

```bash
bash tools/install_bin_link.sh
enhanced-oss-cad examples/sva/assert_raw_delay_pass.sby
enhanced-oss-cad gui --port 8080
```

### Run The Smoke Test

```bash
bash tools/smoke_test.sh
```

The smoke test currently does:

- Python bytecode compilation for the tool scripts
- wrapper CLI tests
- lowerer tests
- `.sby` staging/wrapper tests
- one live `sby` run if `sby` is installed
- one live `ebmc` run if `ebmc` is installed

## Typical Usage Patterns

### Direct RTL File

```bash
./formal path/to/design.sv --top top_name --mode bmc --depth 20
```

### Existing `.sby` Project

```bash
./formal path/to/project.sby
./formal path/to/project.sby prove
```

### Compatibility Mode For Verific-Gated Inputs

```bash
./formal path/to/project.sby prove --compat
```

`--compat` maps to the wrapper’s `--strip-verific` mode, which comments out
`read -verific` in the generated copy without modifying the original source
tree.

## Example Corpus

The `examples/sva/` directory is not just demo material. It is intended as a
regression corpus for the supported subset.

It includes both passing and failing examples for:

- raw delay properties
- named sequences
- nested sequences
- `disable iff`
- bounded repetition
- goto repetition
- nonconsecutive repetition
- mixed `assume` + `assert`
- `cover` hit and miss cases

See [examples/sva/README.md](examples/sva/README.md) for the full list.

## CI And Push Gating

This repo has two levels of protection:

- GitHub CI:
  [`.github/workflows/smoke.yml`](.github/workflows/smoke.yml) runs the smoke test on every push and pull request.
- Local push gate:
  [`.githooks/pre-push`](.githooks/pre-push) runs the same smoke test before a local `git push`.

Enable the repo-local hook in a clone with:

```bash
bash tools/install_git_hooks.sh
```

If you want GitHub to reject merges until CI passes, add branch protection for
the `smoke` workflow in the repository settings.

## Repository Layout

- [formal](formal)
  Thin shell entrypoint for the wrapper.
- [tools/sva_lower.py](tools/sva_lower.py)
  SVA lowering engine.
- [tools/sva_sby.py](tools/sva_sby.py)
  `.sv` / `.sby` wrapper and backend selection logic.
- [tools/SVA_FRONTEND.md](tools/SVA_FRONTEND.md)
  Detailed implementation notes and current technical limits.
- [examples/sva](examples/sva)
  Runnable assertion corpus.

## Current Limits

This is still prototype code. The local lowering path is intentionally scoped
and does not yet cover full SVA or full SystemVerilog assertion syntax.

Known limits include:

- nested or composed properties beyond the current bounded subset
- general ranged-delay and repetition forms outside the implemented patterns
- exact unbounded lowering for `[->]` and `[=]`
- multi-clock properties
- multiple default clocking / default disable declarations or scoped redefinition
- `throughout` beyond the current exact-delay rhs subset
- labeled concurrent action statements on the local lowering path
- bare multicycle `assert property` without an implication wrapper
- full multi-module lowering in one pass

Those cases should use the optional `ebmc` path or remain outside the current
supported set.

## TODO / Roadmap

The next frontend targets are the operators and behaviors that are currently
outside the safe local lowering subset. The active backlog is also tracked in
[TODO.md](TODO.md).

Priority SVA work:

- `within`
- `intersect`
- `first_match`
- `until` and `until_with`
- `accept_on`, `reject_on`, `sync_accept_on`, and `sync_reject_on`
- `nexttime`, `s_nexttime`, and `s_eventually`

Lowering and infrastructure work:

- exact unbounded automata for `[->]` and `[=]`, instead of the current bounded encoding
- broader `throughout` coverage for ranged-delay rhs sequences and more complex composition
- labeled concurrent action statements and attributes before action statements
- scoped or repeated `default clocking` / `default disable iff` handling
- support for bare multicycle `assert property` sequence forms
- stronger multi-module lowering and bind handling
- multi-clock property support

Until those land, the intended behavior is:

- lower the bounded subset locally
- route unsupported operators to the optional `ebmc` backend when possible
- keep the unsupported surface explicit instead of silently mis-modeling it

## Status

This repository is useful for experimentation, regression testing, and frontend
prototyping. It is not a drop-in replacement for a complete SystemVerilog
assertion frontend.
