# SVA Frontend Prototype

This directory contains a repo-local workaround for the lack of concurrent SVA
support in the current OSS CAD `yosys-slang` + `sby` flow.

## What It Does

`sva_lower.py` lowers a small SVA subset into Yosys-compatible formal code:

- `sequence NAME; TERM [##N TERM]...; endsequence`
- simple ranged-delay sequences such as `TERM ##[M:N] TERM`
- `property NAME; @(posedge clk) A |=> B; endproperty`
- `property NAME; @(posedge clk) A |-> B; endproperty`
- simple bounded-range implication consequents such as `A |-> ##[M:N] B`
- bounded-repeat implication consequents such as `A |-> B[*M:N]`
- chained bounded-repeat consequents such as `A |-> B[*M:N] ##K C`
- optional `disable iff (expr)`
- `assert property (NAME);`
- `assume property (NAME);`
- `cover property (NAME);`

The lowered output replaces the unsupported SVA syntax with `always @(posedge
clk)` blocks and immediate `assert(...)`, `assume(...)`, or `cover(...)`
statements under `` `ifdef FORMAL ``.

For operators outside that subset, `sva_sby.py` can now switch to an `ebmc`
backend instead of forcing the source through the lowerer. That keeps the same
`.sv` / `.sby` front-end while avoiding incorrect source rewriting for full-SVA
operators such as goto repetition `[->]` and nonconsecutive repetition `[=]`.

## Wrapper

`sva_sby.py` is a backend wrapper:

1. use the local lowerer and generate a simple `.sby`, or
2. route the job to `ebmc` when full-SVA operators require it

It also accepts an existing `.sby` file, lowers the listed `.sv` sources into a
generated workdir, rewrites the source-carrying sections to point at the
lowered files, and then runs `sby` on that generated config.

In `auto` mode it chooses the lowering path for the supported subset and falls
back to `ebmc` for operators the lowerer does not model safely.

When the `ebmc` backend is selected for a `.sby` task, the wrapper preserves
the `.sby` front-end shape (`mode`, `depth`, `top`, selected task, and solver
when it maps cleanly), but the actual checking semantics come from `ebmc`.
In particular, `prove` currently runs as a bound-driven `ebmc` check up to the
configured depth rather than reimplementing an `sby` induction engine.

In `.sby` mode it preserves the native SymbiYosys config structure instead of
trying to replace it. In practice that means:

- `[options]`, `[engines]`, and `[tasks]` stay in the `.sby` file
- task names after the input file are forwarded to `sby`
- `[files]` entries are restaged with the original destination names preserved
- `[file name.sv]` verbatim sections are lowered in place when they contain SVA
- `bind target helper inst (.*);` is rewritten into a normal helper-module
  instantiation inside the generated target module

There is also an opt-in compatibility path for some upstream examples that rely
on `read -verific` but otherwise fit the lowered subset:

- `--strip-verific` comments out `read -verific` lines in the generated `.sby`
  without modifying the original file

It assumes `sby` is already on `PATH`, for example:

```bash
python3 tools/sva_sby.py /path/to/input.sv --top top_module --engine "smtbmc yices"
python3 tools/sva_sby.py /path/to/input.sby --workdir build/sva_from_sby
python3 tools/sva_sby.py /path/to/input.sby prove --workdir build/sva_from_sby_prove
python3 tools/sva_sby.py /path/to/input.sby prove --strip-verific --workdir build/sva_from_sby_prove
python3 tools/sva_sby.py /path/to/full_sva_input.sby prove --backend auto --workdir build/full_sva
```

For shorter day-to-day use there is also a repo-local wrapper:

```bash
./formal examples/sva/assert_raw_delay_pass.sby
./formal /tool/formal_tools/oss-cad-suite/examples/abstract/props.sby prv --compat
./formal examples/sva/assert_raw_delay_pass.sv
./formal example assert_raw_delay_pass --tool both
./formal compare-native --timeout 20 --jobs 4
```

When `./formal` is given a `.sby` or `.sv` path directly it defaults to the
`sby` subcommand, infers `--top` from the filename for direct `.sv` input, and
creates a default workdir under `build/formal_runs/`.

## Current Limits

This is still a prototype, not a full SystemVerilog parser. The local lowering
path currently does not handle:

- nested / composed properties
- general ranged-delay and repetition forms beyond the simple subset above
- multi-clock properties
- multicycle bare `assert property` without an implication wrapper
- lowering multiple-module files in one pass

Those cases should go through the `ebmc` backend instead of the lowerer.

## Current Result

The prototype has been validated on:

- a nontrivial `req |=> ack` assertion that produces the expected failing trace
- named sequences with `##N`
- `assert property`, `assume property`, and `cover property`

Run the local tests with:

```bash
python3 tools/test_sva_lower.py
```

Cross-check the local lowering path against `ebmc` with:

```bash
python3 tools/compare_ebmc_sby.py
```

That comparison matrix currently matches on the supported subset across
`assert`, `assume`, `cover`, `|->`, `|=>`, fixed `##N`, named sequences, and
`disable iff`. The two remaining EBMC-only forms in the matrix are:

- inline anonymous properties such as `assert property (@(...))`
- multicycle bare `assert property` without an implication wrapper
