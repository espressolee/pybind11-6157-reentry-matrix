# Re-run at PR head 23f2d0a7 (2026-09-03)

Same probe, same producer/consumer sources, same compile line as the 2026-09-02
matrix in `../results/`. What changed is the set of pybind11 trees under test:

```
v12   5e9611aa   legacy consumer, internals 12                 (unchanged)
old   4455e3f4   the unbumped PR head that terminated          (same-run reference)
new   23f2d0a7   bump reverted + destructor/rollback recovery  (under review)
```

The question: does 23f2d0a7 turn the pointer-only mixed-version `std::terminate`
into a catchable failure without changing the other arms.

## Result

macOS arm64, Apple clang 21.0.0, `-O1 -g -fvisibility=hidden`, CPython 3.14.6 and
3.14.0rc1 free-threaded, 20 fresh processes per cell. Both interpreters agree on
every cell.

| trace | producer + consumer | 4455e3f | 23f2d0a7 |
| --- | --- | --- | --- |
| pointer-only | patched + v12 | `std::terminate` 20/20 | `__init__` raises `RuntimeError`; instance left unconstructed, `get()` raises `ValueError` 20/20 |
| pointer-only | v12 + v12 | completes 20/20 | completes 20/20 |
| pointer-only | patched + patched | `ValueError` rejection 20/20 | same 20/20 |
| deref | patched + v12 | SIGSEGV 20/20 | SIGSEGV 20/20 |
| deref | v12 + v12 | SIGSEGV 20/20 | SIGSEGV 20/20 |
| both | v12 producer + 23f2d0a7 consumer | — | identical to pure v12 |

stderr stayed empty in every 23f2d0a7 cell; no unraisable cleanup report was
observed. `nm -gU` on every built module shows no exported `load_value`, which
rules out exported-symbol interposition between the arms.

## Files

- `matrix-3.14.json`, `matrix-3.14t.json` — full records including one sample
  stdout/stderr per verdict; tree paths replaced by labels
- `build_and_run_23f2d0a7.py` — the runner; reads sources from `../harness/`,
  expects the three trees under `../trees/`
- `materialize_23f2d0a7.py` — how the 23f2d0a7 tree was produced: the pinned
  14e32ae tarball from `../RECEIPT.json` plus GitHub's compare diff
  `14e32ae2...23f2d0a7`, then every changed file's git blob sha verified
  against the contents API at 23f2d0a7 (16/16)

## What this does not establish

One toolchain, one OS. The Linux/gcc control from the 09-02 matrix was not
repeated. The rollback with `smart_holder`, custom allocators, or multiple
inheritance was not exercised; only the two traces above were.
