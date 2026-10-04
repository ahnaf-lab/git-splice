import unittest
from pathlib import Path
from typing import List

from git_splice.clustering import PatchSet, cluster_hunks
from git_splice.diff_parser import parse_unified_diff
from git_splice.hunk_graph import HunkGraph
from git_splice.render import render_stack
from git_splice.stack_graph import StackEdge

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _patch_sets_for_fixture(name: str) -> List[PatchSet]:
    diff_text = (FIXTURES_DIR / name).read_text()
    file_diffs = parse_unified_diff(diff_text)
    graph = HunkGraph.build(file_diffs)
    return cluster_hunks(graph)


class TestRenderStack(unittest.TestCase):
    def test_empty_stack_renders_a_plain_message(self):
        self.assertEqual(render_stack([]), "No patch sets to render.")

    def test_every_patch_set_gets_its_own_box(self):
        patch_sets = _patch_sets_for_fixture("multi_file.diff")
        output = render_stack(patch_sets)
        self.assertEqual(output.count("patch set 1"), 1)
        self.assertEqual(output.count("patch set 2"), 1)

    def test_box_lists_files_and_hunk_count(self):
        patch_sets = _patch_sets_for_fixture("multi_file.diff")
        output = render_stack(patch_sets)
        self.assertIn("files: a.py, b.py", output)
        self.assertIn("hunks: 3", output)

    def test_dependent_patch_sets_get_a_labeled_arrow(self):
        patch_sets = _patch_sets_for_fixture("far_apart_same_file.diff")
        output = render_stack(patch_sets)
        self.assertIn("v (module.py)", output)

    def test_independent_patch_sets_get_an_unlabeled_arrow(self):
        patch_sets = _patch_sets_for_fixture("multi_file.diff")
        output = render_stack(patch_sets)
        lines = output.splitlines()
        arrow_lines = [line for line in lines if line.strip() == "v"]
        self.assertEqual(len(arrow_lines), 1)

    def test_output_is_deterministic_across_runs(self):
        patch_sets = _patch_sets_for_fixture("far_apart_same_file.diff")
        self.assertEqual(render_stack(patch_sets), render_stack(patch_sets))

    def test_conflicting_edges_are_reported_as_a_note_not_an_exception(self):
        patch_sets = _patch_sets_for_fixture("far_apart_same_file.diff")
        # Fabricate a genuine cycle (edges pointing both ways) to confirm
        # render_stack surfaces the conflict instead of raising.
        cyclic_edges = [
            StackEdge(before=1, after=2, files=("module.py",)),
            StackEdge(before=2, after=1, files=("other.py",)),
        ]
        output = render_stack(patch_sets, edges=cyclic_edges)
        self.assertIn("ordering conflicts could not be fully resolved", output)

    def test_box_borders_are_well_formed(self):
        patch_sets = _patch_sets_for_fixture("multi_file.diff")
        output = render_stack(patch_sets)
        border_lines = [line for line in output.splitlines() if line.startswith("+")]
        for line in border_lines:
            self.assertTrue(line.startswith("+") and line.endswith("+"))


if __name__ == "__main__":
    unittest.main()
