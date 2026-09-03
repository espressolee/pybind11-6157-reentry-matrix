# Re-run at PR head 89a5f72e (2026-09-03)

`89a5f72e` is henryiii's `refactor: simplify old-style constructor storage
tracking` on top of `23f2d0a7`: 181 insertions, 318 deletions, of which
`include/pybind11/detail/type_caster_base.h` is 75 / 141. It removes the
permission guard classes, hoists `deallocate_instance_value` out, and drops the
nested critical sections in favour of the dispatcher's `constructor_lock`.

Same probe, same producer/consumer sources, same compile line as `../results/`
and `../results-23f2d0a7/`. The question is narrow: **did the refactor change any
measured outcome?**

## Result: no cell moved

macOS arm64, Apple clang 21.0.0, `-O1 -g -fvisibility=hidden`, CPython 3.14.6 and
3.14.0rc1 free-threaded, 20 fresh processes per cell. Both interpreters agree,
and every cell matches `23f2d0a7` exactly.

| trace | producer + consumer | 23f2d0a7 | 89a5f72e |
| --- | --- | --- | --- |
| pointer-only | patched + v12 | `RuntimeError` from `__init__`, `get()` → `ValueError` 20/20 | same 20/20 |
| pointer-only | v12 + v12 | completes 20/20 | completes 20/20 |
| pointer-only | patched + patched | `ValueError` rejection 20/20 | same 20/20 |
| deref | patched + v12 | SIGSEGV 20/20 | SIGSEGV 20/20 |
| deref | v12 + v12 | SIGSEGV 20/20 | SIGSEGV 20/20 |
| both | v12 producer + new consumer | same outcomes as pure v12 | same |

`4455e3f` (the unbumped head that terminated on 09-02) is carried in every run as
a same-run reference and still reaches `std::terminate` on the pointer-only
trace, so the rig is still able to show that failure when it is present.

stderr stayed empty in every `89a5f72e` cell. `nm -gU` on each built module shows
no exported `load_value`, which rules out exported-symbol interposition.

## Files

- `matrix-3.14.json`, `matrix-3.14t.json` — full records with one sample
  stdout/stderr per verdict; tree paths replaced by labels
- `build_and_run_89a5f72e.py` — the runner; sources from `../harness/`, trees
  expected under `../trees/`
- `materialize_89a5f72e.py` — the pinned `14e32ae` tarball plus GitHub's compare
  diff `14e32ae2...89a5f72e`, with all 18 changed files verified by git blob sha
  against the contents API

## What this does not establish

Two traces of one scenario, one toolchain, one OS. It does not run pybind11's own
test suite, and does not exercise `smart_holder`, custom allocators, or multiple
inheritance. "No cell moved" is evidence that the refactor preserved behaviour
here; it is not a general equivalence claim.
