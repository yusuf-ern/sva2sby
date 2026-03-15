# enhanced-oss-cad

Prototype work for extending the OSS CAD formal flow with better SystemVerilog
Assertion handling.

## Overview

This repo contains a local SVA frontend and standalone wrapper around `sby`:

- `tools/sva_lower.py`: lowers a supported SVA subset into Yosys-compatible
  formal RTL under `` `ifdef FORMAL ``
- `tools/sva_sby.py`: stages `.sv` or `.sby` inputs and runs the formal flow
- `formal`: the primary user-facing CLI
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

Make sure `sby` is on `PATH`. If you want the optional full-SVA fallback path,
also make sure `ebmc` is on `PATH`.

Run the local tests:

```bash
python3 tools/test_sva_lower.py
python3 tools/test_sva_sby.py
python3 tools/test_formal.py
```

Run the standalone wrapper:

```bash
./formal examples/sva/assert_raw_delay_pass.sby
./formal examples/sva/assert_raw_delay_pass.sv
```

## Layout

- `tools/SVA_FRONTEND.md`: implementation notes and current limits
- `examples/sva/README.md`: example list and example commands

## Status

This is still prototype code. It is useful for experimentation and regression
testing, but it is not a complete SystemVerilog parser or a complete SVA
implementation.
