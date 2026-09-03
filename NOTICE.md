# Licence and third-party notice

## Scope of `LICENSE`

The MIT licence in `LICENSE` covers the harness and documentation in this
repository. It does **not** cover `third_party/pybind11/`, which is
redistributed under pybind11's own BSD-3-Clause licence — see below.

The measured records under `results/`, `results-23f2d0a7/` and
`results-89a5f72e/` are what particular runs produced. Re-running the harness
makes new bytes, not these; if you cite the numbers, cite the run.

## Third-party notice

This repository is a test harness for a question about
[pybind11](https://github.com/pybind/pybind11), which is distributed under the
BSD-3-Clause licence. See `third_party/pybind11/LICENSE`.

The following files reproduce or derive from pybind11 source:

| file | relationship |
| --- | --- |
| `harness/make_patched_tree.py` | contains a verbatim excerpt of `include/pybind11/detail/type_caster_base.h` used as a patch anchor, and the replacement text |
| `harness/make_instrumented_tree.py` | same, for an instrumentation variant |

Everything else — `harness/producer.cpp`, `harness/consumer.cpp`,
`harness/shared.hpp`, `harness/probe.py`, `harness/build_and_run.py`,
`harness/Dockerfile.linux`, and everything under `results/` — is original to
this repository.

The pybind11 source trees themselves are **not** redistributed here. They are
identified by commit and, for the one subtree that is not available as a release
tarball, by digest. See `BUILD.md`.
