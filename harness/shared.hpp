#pragma once

// Polymorphic on purpose: the reported bug reads a garbage vtable pointer out of
// lazily allocated, never-constructed storage. A trivially copyable struct would
// silently return a garbage int instead of faulting, which would make the pure-v12
// baseline arm unreadable.
struct Shared {
    explicit Shared(int value_in) : value(value_in) {}
    virtual ~Shared() = default;
    virtual int get() const { return value; }
    int value;
};
