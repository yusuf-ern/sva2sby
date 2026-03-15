# SVA Assertion Examples

These example files are the assertion-focused cases for the standalone wrapper
and the optional `ebmc` cross-check path.

Files:

- `assume_assert_overlap.sv`
- `assume_assert_overlap.sby`
- `assume_assert_overlap_fail.sv`
- `assume_assert_overlap_fail.sby`
- `assume_assert_named_delay.sv`
- `assume_assert_named_delay.sby`
- `assume_assert_named_delay_fail.sv`
- `assume_assert_named_delay_fail.sby`
- `assert_disable_iff_fail.sv`
- `assert_disable_iff_fail.sby`
- `assert_raw_delay_pass.sv`
- `assert_raw_delay_pass.sby`
- `assert_raw_delay_tasks.sby`
- `assert_raw_delay_fail.sv`
- `assert_raw_delay_fail.sby`
- `assert_goto_fail.sv`
- `assert_goto_fail.sby`
- `assert_named_delay_pass.sv`
- `assert_named_delay_pass.sby`
- `assert_named_delay_fail.sv`
- `assert_named_delay_fail.sby`
- `assert_nested_sequence_fail.sv`
- `assert_nested_sequence_fail.sby`
- `assert_nested_sequence_pass.sv`
- `assert_nested_sequence_pass.sby`
- `assert_goto_pass.sv`
- `assert_goto_pass.sby`
- `assert_nonconsecutive_fail.sv`
- `assert_nonconsecutive_fail.sby`
- `assert_multi_all_pass.sv`
- `assert_multi_all_pass.sby`
- `assert_multi_one_fail.sv`
- `assert_multi_one_fail.sby`
- `assert_nonconsecutive_pass.sv`
- `assert_nonconsecutive_pass.sby`
- `assert_repeat_tail_fail.sv`
- `assert_repeat_tail_fail.sby`
- `assert_repeat_tail_pass.sv`
- `assert_repeat_tail_pass.sby`
- `assert_disable_iff_pass.sv`
- `assert_disable_iff_pass.sby`
- `cover_same_cycle_hit.sv`
- `cover_same_cycle_hit.sby`
- `cover_same_cycle_miss.sv`
- `cover_same_cycle_miss.sby`
- `cover_disable_iff_miss.sv`
- `cover_disable_iff_miss.sby`
- `cover_named_delay_hit.sv`
- `cover_named_delay_hit.sby`
- `cover_named_delay_miss.sv`
- `cover_named_delay_miss.sby`
- `cover_disable_iff_hit.sv`
- `cover_disable_iff_hit.sby`
- `mux2x1.sv`
- `mux2x1.sby`

Use the wrapper at the repo root:

```bash
./formal examples/sva/assert_raw_delay_pass.sby
./formal examples/sva/assert_raw_delay_pass.sv
./formal examples/sva/assert_goto_pass.sby bmc
./formal examples/sva/assert_goto_pass.sby prove
./formal examples/sva/assert_goto_fail.sby bmc
./formal examples/sva/assert_goto_fail.sby prove
./formal examples/sva/assert_nonconsecutive_pass.sby bmc
./formal examples/sva/assert_nonconsecutive_pass.sby prove
./formal examples/sva/assert_nonconsecutive_fail.sby bmc
./formal examples/sva/assert_nonconsecutive_fail.sby prove
```

If you prefer a real `.sby` file, use the wrapper on the example config:

```bash
python3 tools/sva_sby.py examples/sva/assert_raw_delay_pass.sby --workdir build/example_runs/assert_raw_delay_pass_from_sby
python3 tools/sva_sby.py examples/sva/cover_named_delay_hit.sby --workdir build/example_runs/cover_named_delay_hit_from_sby
python3 tools/sva_sby.py examples/sva/assert_goto_pass.sby --workdir build/example_runs/assert_goto_pass_from_sby
python3 tools/sva_sby.py examples/sva/assert_goto_fail.sby --workdir build/example_runs/assert_goto_fail_from_sby
```

The wrapper also forwards task names to `sby`, so the `.sby` file can control
mode and solver selection directly:

```bash
python3 tools/sva_sby.py examples/sva/assert_raw_delay_tasks.sby prove --workdir build/example_runs/assert_raw_delay_tasks_prove
python3 tools/sva_sby.py examples/sva/assert_raw_delay_tasks.sby cover --workdir build/example_runs/assert_raw_delay_tasks_cover
./formal examples/sva/assert_raw_delay_tasks.sby prove
./formal examples/sva/assert_raw_delay_tasks.sby cover
```

Or run the tools directly:

```bash
ebmc examples/sva/assert_raw_delay_pass.sv --top assert_raw_delay_pass --bound 4 --trace
python3 tools/sva_sby.py examples/sva/assert_raw_delay_pass.sv --top assert_raw_delay_pass --workdir build/example_runs/assert_raw_delay_pass_sby --mode bmc --depth 4 --engine "smtbmc yices"
```

The local lowering path now includes depth-bounded support for goto repetition
`[->]` and nonconsecutive repetition `[=]` on the pure `sby` path. These
examples have both:

- `bmc` using `smtbmc yices`
- `prove` using `smtbmc yices`

```bash
./formal examples/sva/assert_goto_pass.sby bmc
./formal examples/sva/assert_goto_pass.sby prove
./formal examples/sva/assert_goto_fail.sby bmc
./formal examples/sva/assert_goto_fail.sby prove
./formal examples/sva/assert_nonconsecutive_pass.sby bmc
./formal examples/sva/assert_nonconsecutive_pass.sby prove
./formal examples/sva/assert_nonconsecutive_fail.sby bmc
./formal examples/sva/assert_nonconsecutive_fail.sby prove
```

Standalone failing examples now exist for the supported feature families that
already had passing examples:

- `disable iff`
- nested named sequences
- goto repetition `[->]`
- nonconsecutive repetition `[=]`
- bounded repeat tails `[*M:N] ##K`
- `assume` + `assert`
- `cover ... disable iff` miss cases

For these operators the wrapper keeps the lowering bound equal to the `.sby`
`depth`, but expands the generated `smtbmc prove` depth internally so
k-induction has enough horizon to close.
