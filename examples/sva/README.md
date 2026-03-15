# SVA Assertion Examples

These example files are the assertion-focused cases used while comparing
`ebmc` and the local `sva_sby.py` lowering flow.

Files:

- `assume_assert_overlap.sv`
- `assume_assert_overlap.sby`
- `assume_assert_named_delay.sv`
- `assume_assert_named_delay.sby`
- `assert_raw_delay_pass.sv`
- `assert_raw_delay_pass.sby`
- `assert_raw_delay_tasks.sby`
- `assert_raw_delay_fail.sv`
- `assert_raw_delay_fail.sby`
- `assert_named_delay_pass.sv`
- `assert_named_delay_pass.sby`
- `assert_named_delay_fail.sv`
- `assert_named_delay_fail.sby`
- `assert_nested_sequence_pass.sv`
- `assert_nested_sequence_pass.sby`
- `assert_disable_iff_pass.sv`
- `assert_disable_iff_pass.sby`
- `assert_goto_pass.sv`
- `assert_goto_pass.sby`
- `assert_multi_all_pass.sv`
- `assert_multi_all_pass.sby`
- `assert_multi_one_fail.sv`
- `assert_multi_one_fail.sby`
- `assert_nonconsecutive_pass.sv`
- `assert_nonconsecutive_pass.sby`
- `assert_repeat_tail_pass.sv`
- `assert_repeat_tail_pass.sby`
- `cover_same_cycle_hit.sv`
- `cover_same_cycle_hit.sby`
- `cover_same_cycle_miss.sv`
- `cover_same_cycle_miss.sby`
- `cover_named_delay_hit.sv`
- `cover_named_delay_hit.sby`
- `cover_named_delay_miss.sv`
- `cover_named_delay_miss.sby`
- `cover_disable_iff_hit.sv`
- `cover_disable_iff_hit.sby`
- `mux2x1.sv`
- `mux2x1.sby`

Run one example with the helper:

```bash
python3 tools/run_sva_example.py --tool ebmc assert_raw_delay_pass
python3 tools/run_sva_example.py --tool sby assert_raw_delay_pass
python3 tools/run_sva_example.py --tool both assert_raw_delay_pass
python3 tools/run_sva_example.py --tool sby cover_named_delay_hit
```

There is also a short wrapper at the repo root:

```bash
./formal example assert_raw_delay_pass --tool both
./formal examples/sva/assert_raw_delay_pass.sby
./formal examples/sva/assert_raw_delay_pass.sv
./formal examples/sva/assert_goto_pass.sby prove
./formal examples/sva/assert_nonconsecutive_pass.sby prove
```

If you prefer a real `.sby` file, use the wrapper on the example config:

```bash
python3 tools/sva_sby.py examples/sva/assert_raw_delay_pass.sby --workdir build/example_runs/assert_raw_delay_pass_from_sby
python3 tools/sva_sby.py examples/sva/cover_named_delay_hit.sby --workdir build/example_runs/cover_named_delay_hit_from_sby
python3 tools/sva_sby.py examples/sva/assert_goto_pass.sby prove --workdir build/example_runs/assert_goto_pass_from_sby
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

For operators outside the local lowering subset, `sva_sby.py` and `./formal`
now auto-select an `ebmc` backend while keeping the same `.sv` / `.sby`
interface. The current examples that use this path are:

```bash
./formal examples/sva/assert_goto_pass.sby prove
./formal examples/sva/assert_nonconsecutive_pass.sby prove
```

On the `ebmc` path, a `.sby` `prove` task currently means a bound-driven proof
up to the configured `depth`.
