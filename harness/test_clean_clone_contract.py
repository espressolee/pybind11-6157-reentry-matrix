from __future__ import annotations

import io
import pathlib
import tarfile
import tempfile
import unittest
from unittest import mock

import bootstrap_trees
import build_and_run
from make_instrumented_tree import make_instrumented_tree
from make_patched_tree import AFTER as PATCHED_AFTER
from make_patched_tree import BEFORE
from make_patched_tree import make_patched_tree


def fixture_tree(root: pathlib.Path, text: str = BEFORE) -> pathlib.Path:
    header = root / "include" / "pybind11" / "detail" / "type_caster_base.h"
    header.parent.mkdir(parents=True)
    header.write_text(
        text + "\nPYBIND11_NAMESPACE_BEGIN(PYBIND11_NAMESPACE)\n",
        encoding="utf-8",
    )
    (root / "include" / "pybind11" / "pybind11.h").write_text(
        "// fixture\n", encoding="utf-8"
    )
    return root


class CleanCloneContractTests(unittest.TestCase):
    def test_platform_scope_fails_closed(self) -> None:
        build_and_run.enforce_supported_platform("darwin")
        build_and_run.enforce_supported_platform("linux")
        with self.assertRaises(SystemExit):
            build_and_run.enforce_supported_platform("win32")

    def test_gil_expectation_fails_closed(self) -> None:
        build_and_run.enforce_gil_expectation(False, "disabled")
        build_and_run.enforce_gil_expectation(True, "enabled")
        with self.assertRaises(SystemExit):
            build_and_run.enforce_gil_expectation(True, "disabled")
        with self.assertRaises(SystemExit):
            build_and_run.enforce_gil_expectation(False, "enabled")
        with self.assertRaises(SystemExit):
            build_and_run.enforce_gil_expectation(None, "disabled")

    def test_build_paths_match_bootstrap_and_derived_names(self) -> None:
        root = pathlib.Path("/tmp/trees").resolve()
        paths = build_and_run.tree_paths(root)
        self.assertEqual(paths["v12"], root / "v12")
        self.assertEqual(paths["fix"], root / "fix-unbumped")
        self.assertEqual(paths["v13"], root / "bumped-v13")
        self.assertEqual(paths["fixpatched"], root / "fix-patched")
        self.assertEqual(paths["fixinstr"], root / "fix-instrumented")

    def test_derived_trees_are_created_without_mutating_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            source = fixture_tree(root / "source")
            source_text = (
                source / "include" / "pybind11" / "detail" / "type_caster_base.h"
            ).read_text(encoding="utf-8")
            patched = make_patched_tree(source, root / "patched")
            instrumented = make_instrumented_tree(source, root / "instrumented")
            self.assertEqual(
                (
                    source
                    / "include"
                    / "pybind11"
                    / "detail"
                    / "type_caster_base.h"
                ).read_text(encoding="utf-8"),
                source_text,
            )
            self.assertIn(
                PATCHED_AFTER,
                (
                    patched
                    / "include"
                    / "pybind11"
                    / "detail"
                    / "type_caster_base.h"
                ).read_text(encoding="utf-8"),
            )
            self.assertIn(
                "PB11_PROBE uncaught_exceptions",
                (
                    instrumented
                    / "include"
                    / "pybind11"
                    / "detail"
                    / "type_caster_base.h"
                ).read_text(encoding="utf-8"),
            )

    def test_missing_or_nonunique_anchor_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            missing = fixture_tree(root / "missing", "// no collision anchor")
            duplicate = fixture_tree(root / "duplicate", BEFORE + "\n" + BEFORE)
            with self.assertRaises(SystemExit):
                make_patched_tree(missing, root / "out-missing")
            with self.assertRaises(SystemExit):
                make_patched_tree(duplicate, root / "out-duplicate")

    def test_overlapping_source_and_destination_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            source = fixture_tree(root / "source")
            with self.assertRaises(SystemExit):
                make_patched_tree(source, source)
            with self.assertRaises(SystemExit):
                make_patched_tree(source, source / "child")
            with self.assertRaises(SystemExit):
                make_patched_tree(source, root)

    def test_archive_blob_mismatch_fails_before_success(self) -> None:
        commit = "1" * 40
        data = b"not the expected bytes"
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode="w:gz") as tf:
            info = tarfile.TarInfo("owner-repo-sha/include/example.h")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
        responses = [
            b'{"truncated":false,"tree":[{"path":"include/example.h",'
            b'"type":"blob","sha":"0000000000000000000000000000000000000000"}]}',
            archive.getvalue(),
        ]
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(
            bootstrap_trees, "github_bytes", side_effect=responses
        ):
            with self.assertRaises(SystemExit):
                bootstrap_trees.fetch(
                    "fixture",
                    {"commit": commit, "what": "negative fixture", "tree_sha256": None},
                    pathlib.Path(temp),
                )

    def test_recorded_subtree_pin_mismatch_fails_closed(self) -> None:
        commit = "2" * 40
        data = b"verified blob with the wrong aggregate pin"
        blob = bootstrap_trees.blob_sha1(data)
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode="w:gz") as tf:
            info = tarfile.TarInfo("owner-repo-sha/include/example.h")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
        listing = (
            '{"truncated":false,"tree":[{"path":"include/example.h",'
            f'"type":"blob","sha":"{blob}"}}]}}'
        ).encode()
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(
            bootstrap_trees,
            "github_bytes",
            side_effect=[listing, archive.getvalue()],
        ):
            with self.assertRaises(SystemExit):
                bootstrap_trees.fetch(
                    "fixture",
                    {
                        "commit": commit,
                        "what": "wrong aggregate pin",
                        "tree_sha256": "0" * 64,
                    },
                    pathlib.Path(temp),
                )


if __name__ == "__main__":
    unittest.main()
