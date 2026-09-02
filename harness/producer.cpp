#include <pybind11/pybind11.h>

#include "shared.hpp"

namespace py = pybind11;

// Old-style placement-new __init__ -- the exact construct PR #6157 narrows.
// The int argument is what re-enters Python during conversion.
PYBIND11_MODULE(MODNAME, m) {
    py::class_<Shared> cls(m, "Shared");
    cls.def("__init__", [](Shared &self, int x) { new (&self) Shared(x); });
    cls.def("get", [](const Shared &s) { return s.get(); });
}
