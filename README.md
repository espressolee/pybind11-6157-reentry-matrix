# pybind11 #6157 — cross-extension re-entry harness

A test harness for one question raised on
[pybind/pybind11#6157](https://github.com/pybind/pybind11/pull/6157): when the
old-style placement-new `__init__` fix is built without the internals ABI bump,
does a legacy-v12 consumer module behave the same as a pure-v12 build?

## What it does

A producer module registers a class with an old-style placement-new
`__init__(T &self, int)`. While the `int` argument is converted, `__index__`
re-enters and asks a **second** extension module to load the same, still
unconstructed instance. The consumer never registers the type; it resolves the
producer's registration through the shared internals — which is the boundary
`PYBIND11_INTERNALS_VERSION` governs.

Two traces differ only in whether the re-entrant load touches the object, and
that difference decides the answer.

## Quick start from a clean clone

```sh
python3 harness/run_clean_clone.py \
  --python /path/to/python \
  --runs 20 \
  --output out.json
```

This fetches and verifies the three pinned upstream trees, creates the two
derived trees, builds the complete matrix, and writes the raw JSON result. It
uses only the Python standard library for acquisition; see `BUILD.md` for
compiler, network, Docker, retained-work, manual-stage, and fail-closed GIL-state
details. Free-threaded runs should pass `--expect-gil disabled`.

Current platform scope is macOS and Linux. Windows and other platforms are
explicitly unsupported rather than inferred from a failed compiler command.

## Layout

| path | what |
| --- | --- |
| `harness/run_clean_clone.py` | public one-command entry point: fetch, derive, build, run, and emit JSON |
| `harness/bootstrap_trees.py` | fetches the three pinned pybind11 trees from GitHub and verifies every file's Git blob ID |
| `harness/build_and_run.py` | lower-level entry point: builds module variants and runs every arm in fresh processes |
| `harness/producer.cpp`, `consumer.cpp`, `shared.hpp`, `probe.py` | the fixture |
| `harness/make_*_tree.py` | patched and instrumented variants of the library, used as extra arms |
| `harness/test_clean_clone_contract.py` | path, derived-tree, anchor, and corrupt-archive negative fixtures |
| `harness/Dockerfile.linux` | the ELF/gcc/libstdc++ control |
| `results/` | raw measured output, one file per toolchain plus the sensitivity sweep |
| `RECEIPT.json` | inputs, toolchains, findings, and the claim ceiling |
| `BUILD.md` | how to re-run it |

## What it does not establish

The decisive trace binds a `T&` to storage whose object lifetime has not begun,
which is a lifetime violation even when nothing is read. It measures observable
behavior, not defined behavior, and an execution that already contains UB is a
weak basis for imposing a compatibility requirement. `RECEIPT.json` states the
ceiling in full.

See `NOTICE.md` for the third-party attribution.
