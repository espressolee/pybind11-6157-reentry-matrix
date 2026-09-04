"""Instrument the collision branch to record whether an exception was in flight.

A `__clang_call_terminate` frame proves an exception crossed a non-throwing
boundary. It does not, by itself, prove the destructor ran on the ordinary-return
path rather than during unwinding of some other exception. `std::uncaught_exceptions()`
answers that directly: 0 means nothing was propagating when the destructor ran.
"""

import argparse
import pathlib
import shutil

SCRATCH = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_SRC = SCRATCH / "trees" / "fix-unbumped"
DEFAULT_DST = SCRATCH / "trees" / "fix-instrumented"

BEFORE = """        if (v_h.value_ptr() != nullptr) {
            pybind11_fail("loader_life_support: old-style constructor storage collision");
        }"""

AFTER = """        if (v_h.value_ptr() != nullptr) {
            // INSTRUMENTATION (not upstream): record whether any exception was
            // propagating when this destructor ran. 0 means ordinary return.
            std::fprintf(stderr,
                         "PB11_PROBE uncaught_exceptions=%d\\n",
                         std::uncaught_exceptions());
            std::fflush(stderr);
            pybind11_fail("loader_life_support: old-style constructor storage collision");
        }"""

def make_instrumented_tree(src: pathlib.Path, dst: pathlib.Path) -> pathlib.Path:
    src = src.resolve()
    dst = dst.resolve()
    if src == dst or src in dst.parents or dst in src.parents:
        raise SystemExit("source and destination must be separate sibling trees")
    source_header = src / "include" / "pybind11" / "detail" / "type_caster_base.h"
    if not source_header.is_file():
        raise SystemExit(f"missing source header: {source_header}")

    text = source_header.read_text(encoding="utf-8")
    if text.count(BEFORE) != 1:
        raise SystemExit("instrumentation anchor missing or not unique")
    text = text.replace(BEFORE, AFTER)
    namespace_anchor = "PYBIND11_NAMESPACE_BEGIN(PYBIND11_NAMESPACE)"
    if namespace_anchor not in text:
        raise SystemExit("namespace anchor missing")
    text = text.replace(
        namespace_anchor,
        "#include <cstdio>\n#include <exception>\n\n" + namespace_anchor,
        1,
    )

    if dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst)
    target = dst / "include" / "pybind11" / "detail" / "type_caster_base.h"
    target.write_text(text, encoding="utf-8")
    print(f"instrumented {target}")
    return dst


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--src", type=pathlib.Path, default=DEFAULT_SRC)
    parser.add_argument("--dst", type=pathlib.Path, default=DEFAULT_DST)
    args = parser.parse_args()
    make_instrumented_tree(args.src, args.dst)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
