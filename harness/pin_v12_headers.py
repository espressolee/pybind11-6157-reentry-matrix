"""Copy the legacy-v12 pybind11 headers into the fixture so the matrix is
self-contained. The sealed evidence package for the first review pinned the two
PR tarballs but NOT the v12 consumer tree -- it pointed at a live checkout, which
is why that matrix cannot be re-run. Fix that here.
"""

import hashlib
import pathlib
import shutil
import subprocess

SRC = pathlib.Path("<PROJECTS>/pybind11-review")
DST = pathlib.Path(__file__).resolve().parent.parent / "pybind11-v12-5e9611aa"
EXPECTED = "5e9611aacc0bdd2054aa36800055014ebcd8e805"


def git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(SRC), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


head = git("rev-parse", "HEAD")
if head != EXPECTED:
    raise SystemExit(f"checkout HEAD {head} != expected {EXPECTED}")
dirty = git("status", "--porcelain")
if dirty:
    raise SystemExit("checkout is dirty; refusing to pin a mutable tree")

if DST.exists():
    shutil.rmtree(DST)
DST.mkdir(parents=True)
shutil.copytree(SRC / "include", DST / "include")

digest = hashlib.sha256()
for path in sorted((DST / "include").rglob("*")):
    if path.is_file():
        digest.update(path.relative_to(DST).as_posix().encode())
        digest.update(path.read_bytes())

(DST / "PIN.txt").write_text(
    f"source_repo   https://github.com/pybind/pybind11.git\n"
    f"commit        {head}\n"
    f"subtree       include/\n"
    f"tree_sha256   {digest.hexdigest()}\n",
    encoding="utf-8",
)
print(f"pinned {head} include/ -> {DST}")
print(f"tree_sha256 {digest.hexdigest()}")
