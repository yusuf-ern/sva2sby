#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "smoke: bytecode compile"
python3 -m py_compile tools/*.py

echo "smoke: unit tests"
python3 tools/test_formal.py
python3 tools/test_gui.py
python3 tools/test_sva_lower.py
python3 tools/test_sva_sby.py

if command -v sby >/dev/null 2>&1; then
	echo "smoke: live sby wrapper run"
	./formal examples/sva/assert_raw_delay_pass.sby
else
	echo "smoke: skipping live sby run; sby not on PATH"
fi

if command -v ebmc >/dev/null 2>&1; then
	echo "smoke: live ebmc run"
	ebmc examples/sva/assert_raw_delay_pass.sv --top assert_raw_delay_pass --bound 4 --trace
else
	echo "smoke: skipping live ebmc run; ebmc not on PATH"
fi
