# enhanced-oss-cad

Prototype work for extending the OSS CAD formal flow with better SystemVerilog
Assertion handling.

## Overview

This repo contains a local SVA frontend and wrapper tooling around `sby`:

- `tools/sva_lower.py`: lowers a supported SVA subset into Yosys-compatible
  formal RTL under `` `ifdef FORMAL ``
- `tools/sva_sby.py`: stages `.sv` or `.sby` inputs and runs the formal flow
- `formal`: short wrapper for day-to-day use
- `examples/sva/`: runnable assertion examples and `.sby` configs

The current lowering path supports a bounded subset including:

- named `sequence` / `property`
- `|->` and `|=>`
- fixed delay `##N`
- simple ranged delay `##[M:N]`
- bounded consecutive repetition `[*M:N]`
- simple chained bounded repetition such as `A[*M:N] ##K B`
- `assert property`, `assume property`, and `cover property`
- `disable iff`

For some operators outside that subset, the wrapper currently has an optional
EBMC fallback path.

## Quick Start

Run the local tests:

```bash
python3 tools/test_sva_lower.py
python3 tools/test_sva_sby.py
python3 tools/test_formal.py
```

Run a direct example:

```bash
./formal examples/sva/assert_raw_delay_pass.sby
./formal examples/sva/assert_raw_delay_pass.sv
```

Run the comparison matrix against EBMC:

```bash
python3 tools/compare_ebmc_sby.py
```

## Layout

- `tools/SVA_FRONTEND.md`: implementation notes and current limits
- `examples/sva/README.md`: example list and example commands
- `tools/compare_native_sby_wrapper.py`: compare upstream `.sby` examples
  against the wrapper

## Status

This is still prototype code. It is useful for experimentation and regression
testing, but it is not a complete SystemVerilog parser or a complete SVA
implementation.
