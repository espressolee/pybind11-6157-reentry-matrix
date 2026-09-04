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

import argparse
import pathlib
import shutil

SCRATCH = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_SRC = SCRATCH / "trees" / "fix-unbumped"
DEFAULT_DST = SCRATCH / "trees" / "fix-patched"

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

def make_patched_tree(src: pathlib.Path, dst: pathlib.Path) -> pathlib.Path:
    src = src.resolve()
    dst = dst.resolve()
    if src == dst or src in dst.parents or dst in src.parents:
        raise SystemExit("source and destination must be separate sibling trees")
    source_header = src / "include" / "pybind11" / "detail" / "type_caster_base.h"
    if not source_header.is_file():
        raise SystemExit(f"missing source header: {source_header}")

    text = source_header.read_text(encoding="utf-8")
    if text.count(BEFORE) != 1:
        raise SystemExit("patch anchor missing or not unique")

    if dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst)
    target = dst / "include" / "pybind11" / "detail" / "type_caster_base.h"
    target.write_text(text.replace(BEFORE, AFTER), encoding="utf-8")
    print(f"patched {target}")
    return dst


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--src", type=pathlib.Path, default=DEFAULT_SRC)
    parser.add_argument("--dst", type=pathlib.Path, default=DEFAULT_DST)
    args = parser.parse_args()
    make_patched_tree(args.src, args.dst)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
