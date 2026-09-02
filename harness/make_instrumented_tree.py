"""Instrument the collision branch to record whether an exception was in flight.

A `__clang_call_terminate` frame proves an exception crossed a non-throwing
boundary. It does not, by itself, prove the destructor ran on the ordinary-return
path rather than during unwinding of some other exception. `std::uncaught_exceptions()`
answers that directly: 0 means nothing was propagating when the destructor ran.
"""

import pathlib
import shutil

SCRATCH = pathlib.Path(__file__).resolve().parent.parent
SRC = SCRATCH / "head4455e3f" / "pybind-pybind11-4455e3f"
DST = SCRATCH / "head4455e3f-instr" / "pybind-pybind11-4455e3f-instr"

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

if DST.exists():
    shutil.rmtree(DST)
DST.parent.mkdir(parents=True, exist_ok=True)
shutil.copytree(SRC, DST)

target = DST / "include" / "pybind11" / "detail" / "type_caster_base.h"
text = target.read_text(encoding="utf-8")
if text.count(BEFORE) != 1:
    raise SystemExit("anchor missing or not unique")
text = text.replace(BEFORE, AFTER)

# The header already pulls in <exception> transitively in practice, but be explicit.
anchor = "PYBIND11_NAMESPACE_BEGIN(PYBIND11_NAMESPACE)"
if text.count(anchor) < 1:
    raise SystemExit("namespace anchor missing")
text = text.replace(
    anchor, "#include <cstdio>\n#include <exception>\n\n" + anchor, 1
)
target.write_text(text, encoding="utf-8")
print(f"instrumented {target}")
