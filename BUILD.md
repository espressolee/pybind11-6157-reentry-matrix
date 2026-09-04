# Re-running this matrix

Everything is pinned. All three pybind11 trees are `include/` subtrees of public
commits in `pybind/pybind11`, so nothing outside this repository is needed.

```
legacy v12    5e9611aacc0bdd2054aa36800055014ebcd8e805   internals 12
fix unbumped  4455e3f439bed9e8dd6a04cb87260f7d7486bb02   internals 12
bumped v13    14e32ae23af529df8d82681c2d3064884b259a3c   internals 13
```

source_repo   https://github.com/pybind/pybind11.git
commit        5e9611aacc0bdd2054aa36800055014ebcd8e805
subtree       include/
tree_sha256   42f540ea13e1aaef558a37a03d3899f61d0a148aca352abccb7d33d924d7cd2b


## Steps

Prerequisites: Python 3, a C++17 compiler, the target Python interpreter and
its development headers, and network access to GitHub's public API. A
`GITHUB_TOKEN` is optional and is used only to raise the API rate limit.

## Supported and measured scope

The build harness currently supports macOS and Linux and rejects other
platforms before acquisition or compilation. Windows is not supported: the
fixture and interposition checks currently use POSIX shared-library behavior.

This clean-clone route has been measured on:

- macOS arm64 with CPython 3.14.6, GIL enabled;
- macOS arm64 with CPython 3.14.6t, GIL disabled;
- Linux arm64 with CPython 3.14.7 in `python:3.14-slim`.

Other operating systems, architectures, and Python versions are unmeasured,
not implied failures.

From a clean clone, run one command:

```sh
python3 harness/run_clean_clone.py \
  --python /path/to/python \
  --runs 20 \
  --output out.json
```

For a free-threaded run, make the runtime state an enforced input rather than
an assumption:

```sh
PYTHON_GIL=0 python3 harness/run_clean_clone.py \
  --python /path/to/python3.14t \
  --expect-gil disabled \
  --runs 20 \
  --output out-3.14t.json
```

The runner performs the complete sequence:

1. downloads the three exact upstream trees;
2. verifies every downloaded file against its Git blob ID and checks the
   recorded v12 subtree digest;
3. derives the patched and instrumented trees from the exact unbumped tree;
4. builds all seven extension modules;
5. runs six arms in both probe modes, each execution in a fresh process;
6. requires a non-empty JSON result.

All generated trees and build products use a temporary directory by default.
Use `--keep-work` to retain an automatically allocated directory, or
`--work-dir <path>` to choose one explicitly.

### Manual stages, for debugging

1. `python3 harness/bootstrap_trees.py --out trees`

   Downloads each pinned commit from GitHub, keeps `include/`, and verifies
   **every file's git blob sha1** against the tree listing GitHub reports for
   that same commit before writing it. For `v12` it also recomputes the
   `tree_sha256` above and checks it.

2. `python3 harness/make_patched_tree.py`
3. `python3 harness/make_instrumented_tree.py`
4. `python3 harness/build_and_run.py --trees-root trees --python <interpreter> --runs 20 --output <out.json>`

> **Corrected 2026-09-04.** Step 1 previously read "extract both sibling tarballs
> from `../pybind11-pr6157-4455e3f/`". That package was never published, so the
> first step of this file could not be performed by anyone but its author —
> the repository claimed to be re-runnable and was not. `bootstrap_trees.py`
> replaces it and needs no private input.
>
> `harness/pin_v12_headers.py` is kept: it is what produced the `tree_sha256`
> pin above from a clean local checkout, and `bootstrap_trees.py` reproduces
> its digest recipe exactly so the two agree.

The script builds seven modules -- five producer variants and two consumer
variants -- then runs six arms in two probe modes, each in a fresh process.

## Compile line

```
-std=c++17 -O1 -g -fPIC -fvisibility=hidden -shared -undefined dynamic_lookup -DMODNAME=<module> -I<python include> -I<tree>/include -I<harness> <source> -o <module>.so
```

## Interposition control

`nm -gU` on each built module must show only `PyInit_<name>` and pybind11's
`error_already_set` deleter. If `load_value` appears in the dynamic export table
the modules can interpose on each other and the mixed arm is meaningless.

## Linux control

```
docker build -f harness/Dockerfile.linux -t pb11-reentry:linux harness/
docker run --rm -v /absolute/path/to/clone:/work/reentry-matrix pb11-reentry:linux \
  python3 /work/reentry-matrix/harness/run_clean_clone.py \
    --python python3 --expect-gil enabled --runs 20 --tag linux \
    --output /work/reentry-matrix/out-linux.json
```

The link line drops `-undefined dynamic_lookup` on ELF; `build_and_run.py` keys that
off `sys.platform`.

## Toolchains measured

```
Darwin 25.6.0 arm64
Apple clang version 21.0.0 (clang-2100.1.1.101)   (libc++ (Apple clang default))
Python 3.14.6 (main, Jul 18 2026, 17:05:49) [Clang 22.1.3 ]
Python 3.14.0rc1 free-threading build (main, Jul 23 2025, 00:28:25) [Clang 20.1.4 ]

Linux 6.12.76-linuxkit aarch64
c++ (Debian 14.2.0-19) 14.2.0   (libstdc++.so.6.0.33, glibc 2.41)
Python 3.14.7 (main, Aug 31 2026) [GCC 14.2.0]
```

## A note on placeholders

Machine-specific paths were replaced with `<HOME>`, `<PROJECTS>`, `<WORKDIR>`,
`<SESSION>` and `<EVIDENCE>` before publication. Three helper scripts carry them:

- `harness/pin_v12_headers.py` — point `SRC` at your own pybind11 checkout

`harness/run_clean_clone.py` is the public entry point. It does not require
editing a Python constant or reconstructing the historical directory layout.
