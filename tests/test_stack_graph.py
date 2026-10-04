import unittest
from pathlib import Path
from typing import List

from git_splice.clustering import PatchSet, cluster_hunks
from git_splice.diff_parser import Hunk, parse_unified_diff
from git_splice.hunk_graph import HunkGraph
from git_splice.stack_graph import StackEdge, compute_stack_edges, topological_order

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _patch_sets_for_fixture(name: str) -> List[PatchSet]:
    diff_text = (FIXTURES_DIR / name).read_text()
    file_diffs = parse_unified_diff(diff_text)
    graph = HunkGraph.build(file_diffs)
    return cluster_hunks(graph)


def _make_hunk(hunk_id: int, file_path: str, new_start: int) -> Hunk:
    return Hunk(
        id=hunk_id,
        file_path=file_path,
        old_start=new_start,
        old_count=1,
        new_start=new_start,
        new_count=1,
        section_heading="",
    )


class TestComputeStackEdges(unittest.TestCase):
    def test_no_edges_when_patch_sets_touch_disjoint_files(self):
        patch_sets = _patch_sets_for_fixture("multi_file.diff")
        self.assertEqual(compute_stack_edges(patch_sets), [])

    def test_edge_created_for_patch_sets_sharing_a_file(self):
        patch_sets = _patch_sets_for_fixture("far_apart_same_file.diff")
        edges = compute_stack_edges(patch_sets)
        self.assertEqual(edges, [StackEdge(before=1, after=2, files=("module.py",))])

    def test_edges_from_multiple_shared_files_are_merged(self):
        ps1 = PatchSet(index=1, hunks=[_make_hunk(1, "x.py", 1), _make_hunk(2, "y.py", 1)])
        ps2 = PatchSet(index=2, hunks=[_make_hunk(3, "x.py", 50), _make_hunk(4, "y.py", 50)])
        edges = compute_stack_edges([ps1, ps2])
        self.assertEqual(edges, [StackEdge(before=1, after=2, files=("x.py", "y.py"))])


class TestTopologicalOrder(unittest.TestCase):
    def test_orders_dependent_patch_sets_forward(self):
        patch_sets = _patch_sets_for_fixture("far_apart_same_file.diff")
        edges = compute_stack_edges(patch_sets)
        order, conflicts = topological_order(patch_sets, edges)
        self.assertEqual(order, [1, 2])
        self.assertEqual(conflicts, [])

    def test_independent_patch_sets_keep_index_order(self):
        patch_sets = _patch_sets_for_fixture("multi_file.diff")
        order, conflicts = topological_order(patch_sets, [])
        self.assertEqual(order, [1, 2])
        self.assertEqual(conflicts, [])

    def test_cyclic_dependencies_are_reported_as_conflicts(self):
        # patch set 1 is earlier in x.py but later in y.py than patch set 2,
        # so neither order satisfies both file-sharing constraints.
        ps1 = PatchSet(index=1, hunks=[_make_hunk(1, "x.py", 1), _make_hunk(2, "y.py", 50)])
        ps2 = PatchSet(index=2, hunks=[_make_hunk(3, "x.py", 50), _make_hunk(4, "y.py", 1)])
        edges = compute_stack_edges([ps1, ps2])
        order, conflicts = topological_order([ps1, ps2], edges)
        self.assertEqual(set(order), {1, 2})
        self.assertEqual(len(conflicts), 1)


if __name__ == "__main__":
    unittest.main()
