"""Build a candidate repair of the collision path and make it measurable.

The measured defect: on a storage collision, `cleanup_old_style_init_storage`
calls `pybind11_fail`, which throws out of `~loader_life_support()`. That
destructor has no exception specification and all its members have non-throwing
destructors, so it is implicitly noexcept and the throw calls std::terminate.

The candidate repair reports through Python's unraisable hook instead. It cannot
free the reserved storage: `type_info` carries `operator_new` but no matching
deallocator, and the only available path (`type->dealloc`) requires installing
the pointer into the very slot that is already occupied. So the repair leaks the
reservation and says so.

The point of building it is to test the claim that a non-throwing handler alone
restores compatibility. If the process survives `__init__` but the instance is
left pointing at the other allocation, it does not.
"""

import pathlib
import shutil

SCRATCH = pathlib.Path(__file__).resolve().parent.parent
SRC = SCRATCH / "head4455e3f" / "pybind-pybind11-4455e3f"
DST = SCRATCH / "head4455e3f-patched" / "pybind-pybind11-4455e3f-patched"

BEFORE = """        if (v_h.value_ptr() != nullptr) {
            pybind11_fail("loader_life_support: old-style constructor storage collision");
        }"""

AFTER = """        if (v_h.value_ptr() != nullptr) {
            // CANDIDATE REPAIR (not upstream): this function runs from
            // ~loader_life_support(), which has no exception specification and whose
            // members all have non-throwing destructors, so it is implicitly noexcept.
            // pybind11_fail() therefore does not raise a Python error or a catchable C++
            // exception here -- it calls std::terminate and takes the host process down.
            // Report through Python's unraisable hook instead.
            //
            // The reservation is leaked: type_info exposes operator_new but no matching
            // deallocator, and type->dealloc() would require installing this pointer into
            // the slot that is already occupied.
            old_style_init_storage = nullptr;
            if (PyErr_Occurred() == nullptr) {
                PyErr_SetString(PyExc_RuntimeError,
                                "loader_life_support: old-style constructor storage "
                                "collision; reserved storage leaked");
                PyErr_WriteUnraisable(nullptr);
            }
            return;
        }"""

if DST.exists():
    shutil.rmtree(DST)
DST.parent.mkdir(parents=True, exist_ok=True)
shutil.copytree(SRC, DST)

target = DST / "include" / "pybind11" / "detail" / "type_caster_base.h"
text = target.read_text(encoding="utf-8")
if BEFORE not in text:
    raise SystemExit("anchor not found; the tree is not what this patch expects")
if text.count(BEFORE) != 1:
    raise SystemExit("anchor is not unique")
target.write_text(text.replace(BEFORE, AFTER), encoding="utf-8")
print(f"patched {target}")
