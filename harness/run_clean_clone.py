#!/usr/bin/env python3
"""Fetch, derive, build, and run the complete matrix from a clean clone."""

from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys
import tempfile

from bootstrap_trees import TREES, fetch
from build_and_run import enforce_gil_expectation
from build_and_run import enforce_supported_platform
from build_and_run import interpreter_gil_enabled
from make_instrumented_tree import make_instrumented_tree
from make_patched_tree import make_patched_tree

HERE = pathlib.Path(__file__).resolve().parent


def bootstrap_all(trees_root: pathlib.Path) -> None:
    trees_root.mkdir(parents=True, exist_ok=True)
    for name, spec in TREES.items():
        fetch(name, spec, trees_root)
    source = trees_root / "fix-unbumped"
    make_patched_tree(source, trees_root / "fix-patched")
    make_instrumented_tree(source, trees_root / "fix-instrumented")


def run_matrix(
    python: str,
    runs: int,
    output: pathlib.Path,
    work_root: pathlib.Path,
    tuning: str,
    tag: str,
    verbose: bool,
    expect_gil: str,
) -> None:
    if runs < 1:
        raise SystemExit("--runs must be at least 1")
    enforce_supported_platform(sys.platform)
    enforce_gil_expectation(interpreter_gil_enabled(python), expect_gil)
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    trees_root = work_root / "trees"
    build_root = work_root / "build"
    bootstrap_all(trees_root)

    command = [
        python,
        str(HERE / "build_and_run.py"),
        "--python",
        python,
        "--runs",
        str(runs),
        "--output",
        str(output),
        "--trees-root",
        str(trees_root),
        "--build-root",
        str(build_root),
        "--tuning",
        tuning,
        "--expect-gil",
        expect_gil,
    ]
    if tag:
        command.extend(["--tag", tag])
    if verbose:
        command.append("--verbose")
    subprocess.run(command, check=True)
    if not output.is_file() or output.stat().st_size == 0:
        raise SystemExit(f"matrix completed without a non-empty output: {output}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--output", type=pathlib.Path, default=pathlib.Path("out.json"))
    parser.add_argument("--work-dir", type=pathlib.Path)
    parser.add_argument("--keep-work", action="store_true")
    parser.add_argument("--tuning", default="-O1 -g -fvisibility=hidden")
    parser.add_argument("--tag", default="clean-clone")
    parser.add_argument(
        "--expect-gil",
        choices=("any", "enabled", "disabled"),
        default="any",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.work_dir:
        work_root = args.work_dir.resolve()
        work_root.mkdir(parents=True, exist_ok=True)
        run_matrix(
            args.python,
            args.runs,
            args.output,
            work_root,
            args.tuning,
            args.tag,
            args.verbose,
            args.expect_gil,
        )
        print(f"work directory retained: {work_root}")
        return 0

    if args.keep_work:
        work_root = pathlib.Path(tempfile.mkdtemp(prefix="pb11-reentry-"))
        run_matrix(
            args.python,
            args.runs,
            args.output,
            work_root,
            args.tuning,
            args.tag,
            args.verbose,
            args.expect_gil,
        )
        print(f"work directory retained: {work_root}")
        return 0

    with tempfile.TemporaryDirectory(prefix="pb11-reentry-") as temp:
        run_matrix(
            args.python,
            args.runs,
            args.output,
            pathlib.Path(temp),
            args.tuning,
            args.tag,
            args.verbose,
            args.expect_gil,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
