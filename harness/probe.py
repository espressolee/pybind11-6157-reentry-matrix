"""One re-entry trace. PRODUCER/CONSUMER name the two extension modules to mix.

Sequence: producer starts an old-style placement-new __init__; while its int
argument is being converted, Python re-enters and asks the CONSUMER module to
load the same, still-unconstructed instance.
"""

import json
import os
import sys
import warnings

warnings.simplefilter("ignore")

import importlib  # noqa: E402

producer_name = os.environ["PRODUCER"]
consumer_name = os.environ["CONSUMER"]

record = {"producer": producer_name, "consumer": consumer_name}

try:
    producer = importlib.import_module(producer_name)
except BaseException as exc:  # noqa: BLE001
    record["producer_import"] = f"{type(exc).__name__}: {exc}"
    print(json.dumps(record, sort_keys=True), flush=True)
    raise SystemExit(0)

try:
    consumer = importlib.import_module(consumer_name)
except BaseException as exc:  # noqa: BLE001
    record["consumer_import"] = f"{type(exc).__name__}: {exc}"
    print(json.dumps(record, sort_keys=True), flush=True)
    raise SystemExit(0)

mode = os.environ.get("MODE", "deref")
record["mode"] = mode
load = consumer.read if mode == "deref" else consumer.register_handle

obj = producer.Shared.__new__(producer.Shared)
seen = {}


class Reenter:
    def __index__(self):
        try:
            seen["loaded_value"] = load(obj)
        except BaseException as exc:  # noqa: BLE001
            seen["load_error"] = f"{type(exc).__name__}: {exc}"
        return 7


try:
    obj.__init__(Reenter())
except BaseException as exc:  # noqa: BLE001
    record["ctor"] = f"{type(exc).__name__}: {exc}"
else:
    record["ctor"] = "returned"

record["reentrant_load"] = seen

if hasattr(sys, "_is_gil_enabled"):
    record["gil_enabled"] = sys._is_gil_enabled()

# Emitted BEFORE the object is used, so that a fault during first use is
# distinguishable from a fault on the path under test.
print(json.dumps(record, sort_keys=True), flush=True)

post = {}
try:
    post["get"] = obj.get()
except BaseException as exc:  # noqa: BLE001
    post["get"] = f"{type(exc).__name__}: {exc}"
print(json.dumps({"post_use": post}, sort_keys=True), flush=True)
