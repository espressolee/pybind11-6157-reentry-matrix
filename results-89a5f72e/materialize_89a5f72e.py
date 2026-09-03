"""Materialize pybind11 at 23f2d0a7 from the pinned 14e32ae tarball plus the
GitHub compare diff, then verify every changed file's git blob sha against the
contents API at the target commit. No clone, no move: extraction and patching
happen inside the session scratchpad only.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys
import tarfile

SCRATCH = pathlib.Path(__file__).resolve().parent
WORK = SCRATCH / "trees"
TARBALL = SCRATCH / "trees" / "current-head-14e32ae.tar.gz"  # sha256 cf180cd5…ae33, see RECEIPT.json
OLD = "14e32ae23af529df8d82681c2d3064884b259a3c"
NEW = "89a5f72e"
REPO = "pybind/pybind11"


def blob_sha(path: pathlib.Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def gh(*args: str, accept: str | None = None) -> str:
    cmd = ["gh", "api"]
    if accept:
        cmd += ["-H", f"Accept: {accept}"]
    cmd += list(args)
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    with tarfile.open(TARBALL) as tf:
        top = {m.name.split("/")[0] for m in tf.getmembers()}
        tf.extractall(WORK, filter="data")
    assert len(top) == 1, top
    tree = WORK / top.pop()
    print("extracted", tree)

    diff = gh(f"repos/{REPO}/compare/{OLD[:8]}...{NEW}", accept="application/vnd.github.diff")
    (WORK / "compare.diff").write_text(diff)
    applied = subprocess.run(
        ["patch", "-p1", "--forward", "--batch", "-i", str(WORK / "compare.diff")],
        cwd=tree,
        capture_output=True,
        text=True,
    )
    print(applied.stdout[-2000:])
    if applied.returncode != 0:
        print(applied.stderr[-2000:], file=sys.stderr)
        return 2

    files = json.loads(gh(f"repos/{REPO}/compare/{OLD[:8]}...{NEW}", "--jq", "[.files[].filename]"))
    mismatches = []
    for rel in files:
        local = tree / rel
        remote = json.loads(gh(f"repos/{REPO}/contents/{rel}?ref={NEW}", "--jq", "{sha, status: \"ok\"}"))
        ok = local.is_file() and blob_sha(local) == remote["sha"]
        print(("OK  " if ok else "BAD ") + rel)
        if not ok:
            mismatches.append(rel)
    rejects = list(tree.rglob("*.rej"))
    print(f"changed files verified: {len(files) - len(mismatches)}/{len(files)}; rejects: {len(rejects)}")
    if mismatches or rejects:
        return 3
    final = tree.with_name("pybind-pybind11-89a5f72e")
    tree.rename(final)
    print("tree", final)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
