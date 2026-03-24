# TODO

Recent frontend fixes closed the most common multiline formatting gaps:

- multiline `assert/assume/cover property (...)` on the local lowering path
- multiline `default clocking ... endclocking` and `default disable iff (...)` collection
- EBMC-path normalization for multiline action statements
- EBMC-path application of `default disable iff` to explicitly clocked properties

The remaining backlog is below.

## Next Syntax Gaps

- labeled concurrent action statements such as `foo: assert property (...)`
- attributes before concurrent action statements
- scoped or repeated `default clocking` / `default disable iff` declarations
- multiple concurrent action statements packed onto one physical line
- richer multi-module lowering without falling back to passthrough

## Lowering Work

- exact unbounded automata for `[->]` and `[=]`
- broader `throughout` coverage for ranged-delay rhs sequences and richer composition
- broader composed-property coverage beyond the current bounded subset
- support for bare multicycle `assert property` sequence forms
- multi-clock property support

## Verification Work

- add corpus examples for multiline default-clock/default-disable cases
- add regressions for labeled action statements when lowering support lands
- keep the smoke test covering both `sby` and `ebmc` paths
