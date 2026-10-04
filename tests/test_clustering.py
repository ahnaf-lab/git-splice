import unittest
from pathlib import Path
from typing import List

from git_splice.clustering import PatchSet, cluster_hunks
from git_splice.diff_parser import parse_unified_diff
from git_splice.hunk_graph import HunkGraph

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _patch_sets_for_fixture(name: str) -> List[PatchSet]:
    diff_text = (FIXTURES_DIR / name).read_text()
    file_diffs = parse_unified_diff(diff_text)
    graph = HunkGraph.build(file_diffs)
    return cluster_hunks(graph)


def _shape(patch_sets: List[PatchSet]):
    """A plain, order-sensitive summary suitable for golden comparisons."""
    return [
        [(hunk.file_path, hunk.new_start) for hunk in patch_set.hunks]
        for patch_set in patch_sets
    ]


class TestClusteringGoldenFixtures(unittest.TestCase):
    def test_multi_file_fixture_groups_related_hunks_and_isolates_the_rest(self):
        patch_sets = _patch_sets_for_fixture("multi_file.diff")
        self.assertEqual(
            _shape(patch_sets),
            [
                [("a.py", 1), ("a.py", 5), ("b.py", 1)],
                [("c.py", 1)],
            ],
        )

    def test_far_apart_hunks_in_same_file_become_separate_patch_sets(self):
        patch_sets = _patch_sets_for_fixture("far_apart_same_file.diff")
        self.assertEqual(
            _shape(patch_sets),
            [
                [("module.py", 1)],
                [("module.py", 50)],
            ],
        )

    def test_shared_identifier_chain_collapses_into_one_patch_set(self):
        patch_sets = _patch_sets_for_fixture("shared_identifier_chain.diff")
        self.assertEqual(
            _shape(patch_sets),
            [[("alpha.py", 1), ("beta.py", 20), ("gamma.py", 7)]],
        )

    def test_patch_set_indices_are_sequential_and_one_based(self):
        patch_sets = _patch_sets_for_fixture("multi_file.diff")
        self.assertEqual([ps.index for ps in patch_sets], [1, 2])

    def test_clustering_is_deterministic_across_runs(self):
        first_run = _shape(_patch_sets_for_fixture("multi_file.diff"))
        second_run = _shape(_patch_sets_for_fixture("multi_file.diff"))
        self.assertEqual(first_run, second_run)

    def test_patch_set_files_property_is_sorted_and_deduplicated(self):
        patch_sets = _patch_sets_for_fixture("multi_file.diff")
        self.assertEqual(patch_sets[0].files, ["a.py", "b.py"])

    def test_empty_graph_produces_no_patch_sets(self):
        self.assertEqual(cluster_hunks(HunkGraph.build([])), [])


if __name__ == "__main__":
    unittest.main()
