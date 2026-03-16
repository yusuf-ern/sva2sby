# Repository Guidelines

## Project Structure & Module Organization
`formal` is the top-level CLI entrypoint; it forwards into `tools/formal.py`. Core implementation lives in `tools/`: `sva_lower.py` lowers the supported SVA subset, `sva_sby.py` stages `.sby` projects and selects the backend, and `SVA_FRONTEND.md` documents frontend limits. Tests also live in `tools/` as executable `unittest` scripts: `test_formal.py`, `test_sva_lower.py`, and `test_sva_sby.py`. Use `examples/sva/` as the regression corpus for passing and failing `.sv` and `.sby` cases. Generated runs land in `build/formal_runs/` and should not be committed.

## Build, Test, and Development Commands
Run the wrapper on an existing project with `./formal examples/sva/assert_raw_delay_pass.sby`. Run direct RTL input with `./formal path/to/design.sv --top top_name --mode bmc --depth 20`. The main gate is `bash tools/smoke_test.sh`; it byte-compiles the Python tools, runs all three unit test scripts, then performs live `sby` and `ebmc` checks when those tools are installed. For faster iteration, run a single test file such as `python3 tools/test_sva_lower.py`. Enable the local push gate with `bash tools/install_git_hooks.sh`.

## Coding Style & Naming Conventions
Use Python with 4-space indentation, `snake_case` for functions and modules, and explicit type hints where practical. Follow the existing style: standard-library imports first, short module docstrings, and clear helper names such as `default_workdir_for_input`. Keep shell scripts POSIX-friendly Bash with `set -euo pipefail`. Name new examples descriptively by behavior and expected outcome, for example `assert_feature_pass.sby` or `cover_feature_miss.sv`.

## Testing Guidelines
Add or update tests in the nearest `tools/test_*.py` file and name methods `test_<behavior>`. When changing user-visible lowering or staging behavior, add a matching example in `examples/sva/`. Run `bash tools/smoke_test.sh` before pushing; missing `sby` or `ebmc` is acceptable locally because those live checks auto-skip.

## Commit & Pull Request Guidelines
Recent commits use short imperative subjects such as `Add smoke CI and pre-push hook`. Follow that pattern: start with a verb, keep the subject focused, and avoid mixing unrelated changes. Pull requests should describe the affected flow (`formal`, lowering, staging, or examples), list the commands you ran, and include representative CLI output when behavior changes. Screenshots are usually unnecessary for this repository.
