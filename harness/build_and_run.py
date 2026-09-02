"""Build the producer/consumer variants against three pybind11 trees and run the
paired re-entry matrix.

The point of the pairing: the disputed claim is "mixed behaves identically to pure
v12", so a mixed-arm result is uninterpretable without the pure-v12 arm measured
on the same trace, same host, same interpreter.
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
SCRATCH = HERE.parent

TREES = {
    "v12": SCRATCH / "pybind11-v12-5e9611aa",
    "fix": SCRATCH / "head4455e3f" / "pybind-pybind11-4455e3f",
    "v13": SCRATCH / "head14e32ae" / "pybind-pybind11-14e32ae",
    "fixpatched": SCRATCH
    / "head4455e3f-patched"
    / "pybind-pybind11-4455e3f-patched",
    "fixinstr": SCRATCH / "head4455e3f-instr" / "pybind-pybind11-4455e3f-instr",
}

# (module name, source, tree)
MODULES = [
    ("prod_v12", "producer.cpp", "v12"),
    ("prod_fix", "producer.cpp", "fix"),
    ("prod_v13", "producer.cpp", "v13"),
    ("prod_fixpatched", "producer.cpp", "fixpatched"),
    ("prod_fixinstr", "producer.cpp", "fixinstr"),
    ("cons_v12", "consumer.cpp", "v12"),
    ("cons_fix", "consumer.cpp", "fix"),
]

ARMS = [
    ("pure_v12", "prod_v12", "cons_v12", "baseline: the bug as it ships today"),
    ("mixed_unbumped", "prod_fix", "cons_v12", "the disputed configuration"),
    ("pure_fix", "prod_fix", "cons_fix", "control: fix on both sides"),
    ("bumped_v13", "prod_v13", "cons_v12", "control: does the bump intercept first"),
    (
        "mixed_patched",
        "prod_fixpatched",
        "cons_v12",
        "does a non-throwing collision handler restore compatibility?",
    ),
    (
        "mixed_instrumented",
        "prod_fixinstr",
        "cons_v12",
        "was an exception in flight when the destructor ran?",
    ),
]


def interpreter_include(python: str) -> str:
    out = subprocess.run(
        [python, "-c", "import sysconfig;print(sysconfig.get_paths()['include'])"],
        check=True,
        capture_output=True,
        text=True,
    )
    return out.stdout.strip()


def build(
    python: str, outdir: pathlib.Path, verbose: bool, tuning: list[str]
) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    include = interpreter_include(python)
    for name, source, tree in MODULES:
        tree_root = TREES[tree]
        if not (tree_root / "include" / "pybind11" / "pybind11.h").is_file():
            raise SystemExit(f"missing pybind11 tree for {tree}: {tree_root}")
        target = outdir / f"{name}.so"
        cmd = [
            os.environ.get("CXX", "c++"),
            "-std=c++17",
            *tuning,
            "-fPIC",
            "-shared",
            # Mach-O needs the undefined-symbol escape for the CPython symbols the
            # module resolves from the interpreter at load time; ELF resolves those
            # from the already-loaded executable and rejects the flag.
            *(["-undefined", "dynamic_lookup"] if sys.platform == "darwin" else []),
            f"-DMODNAME={name}",
            f"-I{include}",
            f"-I{tree_root / 'include'}",
            f"-I{HERE}",
            str(HERE / source),
            "-o",
            str(target),
        ]
        if verbose:
            print("  building", name, "against", tree, flush=True)
        completed = subprocess.run(cmd, capture_output=True, text=True)
        if completed.returncode != 0:
            sys.stderr.write(completed.stderr[-4000:])
            raise SystemExit(f"build failed for {name} ({tree})")


def classify(returncode: int, stdout: str, stderr: str) -> str:
    """Score a run.

    The probe prints its main record BEFORE first use of the object, so the
    presence of that line separates "died on the path under test" from "survived
    construction and then died using the result".
    """
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
        signal_name = {11: "SIGSEGV", 6: "SIGABRT", 4: "SIGILL", 10: "SIGBUS"}.get(
            -returncode, f"SIG{-returncode}"
        )
        if "storage collision" in stderr:
            signal_name += "_STORAGE_COLLISION_TERMINATE"
        elif "terminate called" in stderr or "libc++abi" in stderr:
            signal_name += "_TERMINATE"

    # The instrumented build reports whether anything was propagating when the
    # destructor ran; that answer matters most in exactly the runs that abort
    # before printing anything, so it is checked before the no-record early exit.
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

    probe = re.search(r"PB11_PROBE uncaught_exceptions=(\d+)", stderr)
    if probe is not None and signal_name is not None:
        return f"{signal_name}_uncaught_exceptions={probe.group(1)}"
    # The constructor's own outcome is the field that decides whether a run is a
    # clean failure or a silent one. An earlier version of this label omitted it,
    # and the summary was read in place of the record. Never again.
    ctor = main.get("ctor", "?")
    ctor_short = ctor if ctor == "returned" else ctor.split(":")[0]
    head = f"load={head}/init={ctor_short}"

    if "collision; reserved storage leaked" in stderr:
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
    parser.add_argument("--verbose", action="store_true")
    # Sensitivity knobs. Optimization level and symbol visibility are the two build
    # choices that could plausibly move the answer, so they are measurable rather
    # than argued.
    parser.add_argument("--tuning", default="-O1 -g -fvisibility=hidden")
    parser.add_argument("--tag", default="")
    args = parser.parse_args()

    tuning = args.tuning.split()
    tag = pathlib.Path(args.python).name + (f"-{args.tag}" if args.tag else "")
    outdir = HERE / f"build-{tag}"
    print(f"building against {args.python}  tuning={args.tuning}", flush=True)
    build(args.python, outdir, args.verbose, tuning)

    results = {}
    for mode in ("deref", "addr"):
        print(f"-- mode={mode}", flush=True)
        for arm, producer, consumer, note in ARMS:
            env = dict(os.environ)
            env["PRODUCER"] = producer
            env["CONSUMER"] = consumer
            env["MODE"] = mode
            env["PYTHONPATH"] = str(outdir)
            counts = collections.Counter()
            samples = {}
            for _ in range(args.runs):
                completed = subprocess.run(
                    [args.python, str(HERE / "probe.py")],
                    check=False,
                    capture_output=True,
                    text=True,
                    env=env,
                )
                verdict = classify(
                    completed.returncode, completed.stdout, completed.stderr
                )
                counts[verdict] += 1
                samples.setdefault(
                    verdict,
                    {
                        "returncode": completed.returncode,
                        "stdout": completed.stdout.strip()[-600:],
                        "stderr": completed.stderr.strip()[-600:],
                    },
                )
            results[f"{mode}/{arm}"] = {
                "note": note,
                "mode": mode,
                "producer": producer,
                "consumer": consumer,
                "counts": dict(counts),
                "samples": samples,
            }
            rendered = ", ".join(f"{v}x {k}" for k, v in counts.most_common())
            print(f"  {arm:16s} {rendered}", flush=True)

    payload = {
        "python": subprocess.run(
            [args.python, "-c", "import sys;print(sys.version)"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip(),
        "abiflags": subprocess.run(
            [args.python, "-c", "import sys;print(getattr(sys,'abiflags',''))"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip(),
        "ext_suffix": sysconfig.get_config_var("EXT_SUFFIX"),
        "runs_per_arm": args.runs,
        "trees": {k: str(v) for k, v in TREES.items()},
        "results": results,
    }
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
        print("wrote", args.output, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
