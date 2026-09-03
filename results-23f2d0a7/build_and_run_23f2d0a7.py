"""Re-run the paired re-entry matrix against PR #6157 head 23f2d0a7.

Same probe, same producer/consumer sources, same compile line as the sealed
2026-09-02 matrix (sources are read from the sealed harness; nothing there is
modified). What changed is the set of pybind11 trees:

    v12   5e9611aa   legacy consumer, internals 12         (unchanged)
    old   4455e3f4   the unbumped head that terminated     (same-day reference)
    new   23f2d0a7   bump reverted + destructor recovery   (under review)

The question rwgk asked for a review on: does 23f2d0a7 turn the pointer-only
mixed-version std::terminate into a catchable failure, without changing the
other arms.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import pathlib
import re
import subprocess
import sys
import sysconfig

HERE = pathlib.Path(__file__).resolve().parent
SCRATCH = HERE.parent  # repo root; trees/ is materialized per BUILD.md
HARNESS = HERE.parent / "harness"

TREES = {
    "v12": SCRATCH / "trees" / "pybind11-v12-5e9611aa",
    "old": SCRATCH / "trees" / "pybind-pybind11-4455e3f",
    "new": SCRATCH / "trees" / "pybind-pybind11-23f2d0a",
}

MODULES = [
    ("prod_v12", "producer.cpp", "v12"),
    ("prod_old", "producer.cpp", "old"),
    ("prod_new", "producer.cpp", "new"),
    ("cons_v12", "consumer.cpp", "v12"),
    ("cons_old", "consumer.cpp", "old"),
    ("cons_new", "consumer.cpp", "new"),
]

ARMS = [
    ("pure_v12", "prod_v12", "cons_v12", "baseline: the bug as it ships today"),
    ("mixed_old", "prod_old", "cons_v12", "reference: unbumped 4455e3f producer + v12 consumer (terminated on 09-02)"),
    ("mixed_new", "prod_new", "cons_v12", "under review: 23f2d0a producer + v12 consumer"),
    ("pure_old", "prod_old", "cons_old", "control: 4455e3f on both sides"),
    ("pure_new", "prod_new", "cons_new", "control: 23f2d0a on both sides"),
    ("reverse_new", "prod_v12", "cons_new", "reverse direction: v12 producer + 23f2d0a consumer"),
]


def interpreter_include(python: str) -> str:
    out = subprocess.run(
        [python, "-c", "import sysconfig;print(sysconfig.get_paths()['include'])"],
        check=True, capture_output=True, text=True,
    )
    return out.stdout.strip()


def build(python: str, outdir: pathlib.Path, tuning: list[str]) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    include = interpreter_include(python)
    for name, source, tree in MODULES:
        tree_root = TREES[tree]
        if not (tree_root / "include" / "pybind11" / "pybind11.h").is_file():
            raise SystemExit(f"missing pybind11 tree for {tree}: {tree_root}")
        target = outdir / f"{name}.so"
        cmd = [
            os.environ.get("CXX", "c++"), "-std=c++17", *tuning, "-fPIC", "-shared",
            *(["-undefined", "dynamic_lookup"] if sys.platform == "darwin" else []),
            f"-DMODNAME={name}", f"-I{include}", f"-I{tree_root / 'include'}", f"-I{HARNESS}",
            str(HARNESS / source), "-o", str(target),
        ]
        print("  building", name, "against", tree, flush=True)
        completed = subprocess.run(cmd, capture_output=True, text=True)
        if completed.returncode != 0:
            sys.stderr.write(completed.stderr[-4000:])
            raise SystemExit(f"build failed for {name} ({tree})")


def interposition_control(outdir: pathlib.Path) -> dict[str, list[str]]:
    """Each module must export only its PyInit and pybind11's error_already_set
    deleter; if load_value is exported the arms can interpose and mean nothing."""
    report = {}
    for name, _, _ in MODULES:
        out = subprocess.run(["nm", "-gU", str(outdir / f"{name}.so")], capture_output=True, text=True)
        syms = [line.split()[-1] for line in out.stdout.splitlines() if line.strip()]
        report[name] = syms
    return report


def classify(returncode: int, stdout: str, stderr: str) -> str:
    """Identical to the sealed harness classifier, plus a generic unraisable marker:
    rwgk's recovery reports cleanup failures through PyErr_WriteUnraisable with
    messages the 09-02 classifier never saw, so match CPython's hook output rather
    than one spelling."""
    lines = [line for line in stdout.strip().splitlines() if line.strip()]
    main = None
    post = None
    for line in lines:
        try:
            payload = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        if "post_use" in payload:
            post = payload["post_use"]
        else:
            main = payload

    signal_name = None
    if returncode < 0:
        signal_name = {11: "SIGSEGV", 6: "SIGABRT", 4: "SIGILL", 10: "SIGBUS"}.get(-returncode, f"SIG{-returncode}")
        if "storage collision" in stderr:
            signal_name += "_STORAGE_COLLISION_TERMINATE"
        elif "terminate called" in stderr or "libc++abi" in stderr:
            signal_name += "_TERMINATE"

    probe = re.search(r"PB11_PROBE uncaught_exceptions=(\d+)", stderr)
    if probe is not None and signal_name is not None:
        return f"{signal_name}_uncaught_exceptions={probe.group(1)}"

    if main is None:
        return signal_name or (f"EXIT_{returncode}" if returncode else "UNPARSEABLE")

    load = main.get("reentrant_load", {})
    if "load_error" in load:
        head = "REJECTED_" + load["load_error"].split(":")[0]
    elif "loaded_value" in load:
        head = "ACCEPTED"
    elif "consumer_import" in main:
        head = "CONSUMER_IMPORT_" + main["consumer_import"].split(":")[0]
    else:
        head = "NO_REENTRANT_LOAD"

    ctor = main.get("ctor", "?")
    ctor_short = ctor if ctor == "returned" else ctor.split(":")[0]
    head = f"load={head}/init={ctor_short}"

    if "collision; reserved storage leaked" in stderr or "Exception ignored" in stderr:
        head += "+UNRAISABLE"
    if signal_name is not None:
        return f"{head}_SURVIVED_INIT_THEN_{signal_name}"
    if post is not None:
        get = post.get("get")
        head += f"/get={get if isinstance(get, int) else str(get).split(':')[0]}"
    return head


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--output", type=pathlib.Path)
    parser.add_argument("--tuning", default="-O1 -g -fvisibility=hidden")
    parser.add_argument("--tag", default="")
    args = parser.parse_args()

    tuning = args.tuning.split()
    tag = pathlib.Path(args.python).name + (f"-{args.tag}" if args.tag else "")
    outdir = HERE / f"build-{tag}"
    print(f"building against {args.python}  tuning={args.tuning}", flush=True)
    build(args.python, outdir, tuning)
    exports = interposition_control(outdir)
    bad = {k: v for k, v in exports.items() if any("load_value" in s for s in v)}
    if bad:
        raise SystemExit(f"interposition control FAILED: load_value exported by {sorted(bad)}")
    print("interposition control: OK (no module exports load_value)", flush=True)

    results = {}
    for mode in ("deref", "addr"):
        print(f"-- mode={mode}", flush=True)
        for arm, producer, consumer, note in ARMS:
            env = dict(os.environ)
            env.update(PRODUCER=producer, CONSUMER=consumer, MODE=mode, PYTHONPATH=str(outdir))
            counts = collections.Counter()
            samples = {}
            for _ in range(args.runs):
                completed = subprocess.run(
                    [args.python, str(HARNESS / "probe.py")],
                    check=False, capture_output=True, text=True, env=env,
                )
                verdict = classify(completed.returncode, completed.stdout, completed.stderr)
                counts[verdict] += 1
                samples.setdefault(verdict, {
                    "returncode": completed.returncode,
                    "stdout": completed.stdout.strip()[-600:],
                    "stderr": completed.stderr.strip()[-600:],
                })
            results[f"{mode}/{arm}"] = {
                "note": note, "mode": mode, "producer": producer, "consumer": consumer,
                "counts": dict(counts), "samples": samples,
            }
            rendered = ", ".join(f"{v}x {k}" for k, v in counts.most_common())
            print(f"  {arm:12s} {rendered}", flush=True)

    payload = {
        "python": subprocess.run([args.python, "-c", "import sys;print(sys.version)"], check=True, capture_output=True, text=True).stdout.strip(),
        "abiflags": subprocess.run([args.python, "-c", "import sys;print(getattr(sys,'abiflags',''))"], check=True, capture_output=True, text=True).stdout.strip(),
        "ext_suffix": sysconfig.get_config_var("EXT_SUFFIX"),
        "cxx": subprocess.run([os.environ.get("CXX", "c++"), "--version"], capture_output=True, text=True).stdout.splitlines()[0],
        "tuning": args.tuning,
        "runs_per_arm": args.runs,
        "trees": {k: str(v) for k, v in TREES.items()},
        "exports": exports,
        "results": results,
    }
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
        print("wrote", args.output, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
