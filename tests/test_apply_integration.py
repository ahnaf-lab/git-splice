"""Snapshot-style integration test for `--apply`.

Builds a throwaway git repository, creates a messy working-tree diff
across two files with three independent regions of change, runs the
same parse -> graph -> cluster -> stack-order pipeline the CLI uses,
and asserts the exact resulting commit sequence: count, messages (in
order), parent chain, and the file content materialized at each commit.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from git_splice.apply import apply_patch_sets, commit_message
from git_splice.clustering import cluster_hunks
from git_splice.diff_parser import parse_unified_diff
from git_splice.hunk_graph import HunkGraph
from git_splice.stack_graph import compute_stack_edges, topological_order

_ENV_OVERRIDES = {
    "GIT_AUTHOR_NAME": "Test Author",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "Test Author",
    "GIT_COMMITTER_EMAIL": "test@example.com",
}


def _run(args, cwd):
    result = subprocess.run(
        args, cwd=cwd, capture_output=True, text=True, shell=False, check=False
    )
    if result.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} failed: {result.stderr}")
    return result.stdout


class TestApplyIntegration(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="git-splice-apply-test-")
        self.repo_dir = self._tmp.name
        self._old_env = {key: os.environ.get(key) for key in _ENV_OVERRIDES}
        os.environ.update(_ENV_OVERRIDES)
        self._old_cwd = os.getcwd()

        _run(["git", "init", "-q"], cwd=self.repo_dir)
        _run(["git", "config", "user.name", "Test Author"], cwd=self.repo_dir)
        _run(["git", "config", "user.email", "test@example.com"], cwd=self.repo_dir)

        a_lines = [f"line{i}" for i in range(1, 21)]
        b_lines = ["b_only_line"]
        Path(self.repo_dir, "a.py").write_text("\n".join(a_lines) + "\n")
        Path(self.repo_dir, "b.py").write_text("\n".join(b_lines) + "\n")
        _run(["git", "add", "a.py", "b.py"], cwd=self.repo_dir)
        _run(["git", "commit", "-q", "-m", "initial"], cwd=self.repo_dir)
        self.initial_sha = _run(["git", "rev-parse", "HEAD"], cwd=self.repo_dir).strip()

        a_lines[0] = "LINE1_CHANGED"
        a_lines[19] = "LINE20_CHANGED"
        Path(self.repo_dir, "a.py").write_text("\n".join(a_lines) + "\n")
        Path(self.repo_dir, "b.py").write_text("b_only_line_CHANGED\n")
        self.expected_a = "\n".join(a_lines) + "\n"
        self.expected_b = "b_only_line_CHANGED\n"

        os.chdir(self.repo_dir)

    def tearDown(self):
        os.chdir(self._old_cwd)
        for key, value in self._old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmp.cleanup()

    def _ordered_patch_sets(self, file_diffs):
        graph = HunkGraph.build(file_diffs)
        patch_sets = cluster_hunks(graph)
        edges = compute_stack_edges(patch_sets)
        order, conflicts = topological_order(patch_sets, edges)
        self.assertEqual(conflicts, [])
        by_index = {ps.index: ps for ps in patch_sets}
        return [by_index[i] for i in order]

    def test_apply_writes_one_commit_per_independent_patch_set(self):
        diff_text = _run(["git", "diff"], cwd=self.repo_dir)
        file_diffs = parse_unified_diff(diff_text)
        patch_sets = self._ordered_patch_sets(file_diffs)

        # Three disjoint edits (two far apart in a.py, one in b.py) with no
        # shared identifiers should cluster into three independent patch sets.
        self.assertEqual(len(patch_sets), 3)

        records = apply_patch_sets(patch_sets, file_diffs, cached=False)

        self.assertEqual(len(records), 3)
        expected_messages = [commit_message(ps) for ps in patch_sets]
        self.assertEqual([r.message for r in records], expected_messages)

        log_subjects = _run(
            ["git", "log", "--format=%s", "--reverse"], cwd=self.repo_dir
        ).splitlines()
        self.assertEqual(log_subjects, ["initial"] + expected_messages)

        log_shas = _run(
            ["git", "log", "--format=%H", "--reverse"], cwd=self.repo_dir
        ).splitlines()
        self.assertEqual(log_shas, [self.initial_sha] + [r.sha for r in records])

        parents = _run(
            ["git", "log", "--format=%P", "--reverse"], cwd=self.repo_dir
        ).splitlines()
        self.assertEqual(parents[0], "")
        self.assertEqual(parents[1], self.initial_sha)
        self.assertEqual(parents[2], log_shas[1])
        self.assertEqual(parents[3], log_shas[2])

        final_a = _run(["git", "show", f"HEAD:a.py"], cwd=self.repo_dir)
        final_b = _run(["git", "show", f"HEAD:b.py"], cwd=self.repo_dir)
        self.assertEqual(final_a, self.expected_a)
        self.assertEqual(final_b, self.expected_b)

        status = _run(["git", "status", "--porcelain"], cwd=self.repo_dir)
        self.assertEqual(status, "")

        on_disk_a = Path(self.repo_dir, "a.py").read_text()
        self.assertEqual(on_disk_a, self.expected_a)

    def test_apply_on_an_empty_patch_set_list_is_a_no_op(self):
        records = apply_patch_sets([], [], cached=False)
        self.assertEqual(records, [])
        head_after = _run(["git", "rev-parse", "HEAD"], cwd=self.repo_dir).strip()
        self.assertEqual(head_after, self.initial_sha)


if __name__ == "__main__":
    unittest.main()
