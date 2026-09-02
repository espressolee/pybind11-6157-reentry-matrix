#include <pybind11/pybind11.h>

#include <cstdint>
#include <unordered_set>

#include "shared.hpp"

namespace py = pybind11;

// This module never registers Shared; it resolves the producer's registration
// through shared internals. `read` performs the cross-DSO load of the instance.
// The virtual call is what turns an unconstructed object into an observable fault.
PYBIND11_MODULE(MODNAME, m) {
    // `deref` mode: the classic bug shape. The virtual call faults on the garbage
    // vtable of never-constructed storage -- but it kills the process AT the
    // re-entrant load, so nothing downstream of the load is observable.
    m.def("read", [](const Shared &s) { return s.get(); });

    // `addr` mode: perform the same cross-DSO load but do not touch object state.
    // Modelled as pointer-identity bookkeeping -- a registry keyed by address, which
    // is what keep-alive tables, alias checks, non-owning wrappers and "have I seen
    // this object" caches all do. A naked `return &s` would invite the objection
    // that no real binding does that.
    static std::unordered_set<const Shared *> registry;
    m.def("register_handle", [](const Shared *item) {
        registry.insert(item);
        return registry.size();
    });
}
