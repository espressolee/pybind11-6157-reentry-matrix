#!/usr/bin/env python3
"""Fetch the three pinned pybind11 trees straight from GitHub, so a stranger can run this.

Why this exists
---------------
`BUILD.md` step 1 says to extract tarballs from a sibling package
`../pybind11-pr6157-4455e3f/`. That package is not published — it lives only on the author's
machine. So the public repository documents a first step that nobody else can perform, and
"a reproducer anyone can run" was not actually true.

Every tree under test is a public commit in `pybind/pybind11`, so no private input is needed:
this script downloads each pinned commit from GitHub, keeps only `include/`, and verifies what
it got before writing anything.

Verification, in this order
---------------------------
1. the archive is fetched for an exact 40-hex commit, never a branch or tag;
2. every extracted file's **git blob sha1** is recomputed and compared against the tree listing
   GitHub reports for that same commit — so a corrupted or substituted archive is caught;
3. the whole `include/` subtree gets a deterministic sha256 which is printed, and compared
   against the pin in BUILD.md when one is recorded.

A mismatch aborts. Downloading something and hoping it is right is the failure this file
exists to prevent.

Usage
-----
    python3 harness/bootstrap_trees.py --out trees
    python3 harness/bootstrap_trees.py --out trees --only v12

Needs only the standard library and network access to GitHub's public API. Set
`GITHUB_TOKEN` optionally when the anonymous API rate limit is too small.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import pathlib
import shutil
import sys
import tarfile
import urllib.error
import urllib.request

# Pinned commits. Same values as BUILD.md; changing one here changes what is measured.
TREES = {
    "v12": {
        "commit": "5e9611aacc0bdd2054aa36800055014ebcd8e805",
        "what": "legacy v12 consumer, internals 12",
        "tree_sha256": "42f540ea13e1aaef558a37a03d3899f61d0a148aca352abccb7d33d924d7cd2b",
    },
    "fix-unbumped": {
        "commit": "4455e3f439bed9e8dd6a04cb87260f7d7486bb02",
        "what": "the unbumped PR head that terminated",
        "tree_sha256": None,
    },
    "bumped-v13": {
        "commit": "14e32ae23af529df8d82681c2d3064884b259a3c",
        "what": "internals 13",
        "tree_sha256": None,
    },
}
REPO = "pybind/pybind11"
SUBTREE = "include/"


def github_bytes(endpoint: str) -> bytes:
    url = f"https://api.github.com/{endpoint.lstrip('/')}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "pybind11-6157-reentry-matrix",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            return response.read()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        raise SystemExit(f"GitHub request failed for {url}: {exc}") from exc


def blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def github_blob_shas(commit: str) -> dict[str, str]:
    """path -> git blob sha, for every file under include/ at this commit."""
    out = github_bytes(f"repos/{REPO}/git/trees/{commit}?recursive=1")
    tree = json.loads(out)
    if tree.get("truncated"):
        raise SystemExit("GitHub truncated the tree listing; cannot verify completely")
    return {e["path"]: e["sha"] for e in tree["tree"]
            if e["type"] == "blob" and e["path"].startswith(SUBTREE)}


def subtree_sha256(dest: pathlib.Path) -> str:
    """The digest recipe from `pin_v12_headers.py`, reproduced exactly.

    That script walks `sorted((DST/'include').rglob('*'))` and, for each file, feeds the
    POSIX path **relative to DST** (so it starts with `include/`) followed immediately by the
    file bytes — no separator, no per-file hashing. A different recipe here would produce a
    different number for identical content, which is exactly the false alarm this comment
    prevents: the first version of this function used `path\\0sha256(bytes)` and reported a
    mismatch against a tree whose every git blob sha had already verified.
    """
    h = hashlib.sha256()
    for p in sorted((dest / "include").rglob("*")):
        if p.is_file():
            h.update(p.relative_to(dest).as_posix().encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def fetch(name: str, spec: dict, out_root: pathlib.Path) -> pathlib.Path:
    commit = spec["commit"]
    if len(commit) != 40 or not all(c in "0123456789abcdef" for c in commit):
        raise SystemExit(f"{name}: not a full 40-hex commit: {commit!r}")

    print(f"\n=== {name}  {commit[:12]}  ({spec['what']}) ===")
    dest = out_root / name
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    print("  listing tree from GitHub …")
    want = github_blob_shas(commit)
    print(f"    {len(want)} files under {SUBTREE}")

    print("  downloading archive …")
    raw = github_bytes(f"repos/{REPO}/tarball/{commit}")
    print(f"    {len(raw):,} bytes")

    n = 0
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tf:
        for m in tf.getmembers():
            if not m.isfile():
                continue
            # strip the "<owner>-<repo>-<sha>/" prefix GitHub adds
            rel = m.name.split("/", 1)[1] if "/" in m.name else m.name
            if not rel.startswith(SUBTREE):
                continue
            data = tf.extractfile(m).read()
            got, exp = blob_sha1(data), want.get(rel)
            if exp is None:
                raise SystemExit(f"  ✗ {rel} is in the archive but not in the tree listing")
            if got != exp:
                raise SystemExit(f"  ✗ {rel}: blob {got[:12]} != listing {exp[:12]}")
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            n += 1

    missing = set(want) - {str(p.relative_to(dest).as_posix())
                           for p in dest.rglob("*") if p.is_file()}
    if missing:
        raise SystemExit(f"  ✗ {len(missing)} file(s) in the listing never arrived: "
                         f"{sorted(missing)[:3]}")
    print(f"  ✓ {n} files written, every git blob sha matches the commit")

    digest = subtree_sha256(dest)
    pin = spec.get("tree_sha256")
    if pin:
        if digest != pin:
            raise SystemExit(
                f"  ✗ subtree sha256 {digest} != recorded pin {pin}"
            )
        else:
            print(f"  ✓ subtree sha256 matches BUILD.md pin: {digest[:16]}…")
    else:
        print(f"  subtree sha256: {digest}")
    return dest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default="trees", help="directory to write the trees into")
    ap.add_argument("--only", choices=sorted(TREES), help="fetch just one tree")
    args = ap.parse_args()

    out_root = pathlib.Path(args.out).resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    names = [args.only] if args.only else list(TREES)

    made = {}
    for name in names:
        made[name] = str(fetch(name, TREES[name], out_root))

    print("\n=== done ===")
    for name, path in made.items():
        print(f"  {name:<14} {path}")
    print("\nNext:")
    print("  python3 harness/run_clean_clone.py --python <interpreter> --runs 20 "
          "--output out.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
