import unittest

from git_splice.diff_parser import parse_unified_diff
from git_splice.hunk_graph import HunkGraph

MULTI_FILE_DIFF = """\
diff --git a/a.py b/a.py
index 83db48f..bf269f4 100644
--- a/a.py
+++ b/a.py
@@ -1,2 +1,2 @@
-x = 1
+x = helper_function()
@@ -5,2 +5,2 @@
-y = 2
+y = 3
diff --git a/b.py b/b.py
index 1111111..2222222 100644
--- a/b.py
+++ b/b.py
@@ -1,1 +1,1 @@
-z = 0
+z = helper_function()
diff --git a/c.py b/c.py
index 3333333..4444444 100644
--- a/c.py
+++ b/c.py
@@ -1,1 +1,1 @@
-w = 0
+w = totally_unrelated_value
"""


def _build_graph():
    file_diffs = parse_unified_diff(MULTI_FILE_DIFF)
    return HunkGraph.build(file_diffs), file_diffs


class TestHunkGraph(unittest.TestCase):
    def test_graph_contains_every_hunk(self):
        graph, file_diffs = _build_graph()
        total_hunks = sum(len(fd.hunks) for fd in file_diffs)
        self.assertEqual(total_hunks, 4)
        self.assertEqual(len(graph.hunks), 4)

    def test_adjacent_hunks_in_same_file_are_linked(self):
        graph, file_diffs = _build_graph()
        a_hunks = next(fd for fd in file_diffs if fd.path == "a.py").hunks
        first_id, second_id = a_hunks[0].id, a_hunks[1].id
        self.assertIn(second_id, graph.neighbors(first_id))
        self.assertIn("adjacent-lines", graph.neighbors(first_id)[second_id])

    def test_shared_identifier_links_hunks_across_files(self):
        graph, file_diffs = _build_graph()
        a_hunk = next(fd for fd in file_diffs if fd.path == "a.py").hunks[0]
        b_hunk = next(fd for fd in file_diffs if fd.path == "b.py").hunks[0]
        reasons = graph.neighbors(a_hunk.id).get(b_hunk.id)
        self.assertIsNotNone(reasons)
        self.assertIn("shared-identifier:helper_function", reasons)

    def test_connected_components_group_related_hunks(self):
        graph, file_diffs = _build_graph()
        components = graph.connected_components()
        sizes = sorted(len(component) for component in components)
        # a.py's two hunks plus b.py's hunk form one cluster (3 hunks);
        # c.py's hunk shares nothing, so it stands alone.
        self.assertEqual(sizes, [1, 3])

    def test_unrelated_hunk_is_isolated(self):
        graph, file_diffs = _build_graph()
        c_hunk = next(fd for fd in file_diffs if fd.path == "c.py").hunks[0]
        self.assertEqual(graph.neighbors(c_hunk.id), {})

    def test_empty_input_produces_empty_graph(self):
        graph = HunkGraph.build([])
        self.assertEqual(graph.hunks, [])
        self.assertEqual(graph.connected_components(), [])


if __name__ == "__main__":
    unittest.main()
