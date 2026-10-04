import unittest

from git_splice.apply import commit_message, reconstruct_file_lines
from git_splice.clustering import PatchSet
from git_splice.diff_parser import Hunk


def _hunk(old_start, old_count, new_start, new_count, body_lines, file_path="a.py"):
    hunk = Hunk(
        id=0,
        file_path=file_path,
        old_start=old_start,
        old_count=old_count,
        new_start=new_start,
        new_count=new_count,
        section_heading="",
    )
    hunk.body_lines = body_lines
    return hunk


class TestReconstructFileLines(unittest.TestCase):
    def test_full_application_matches_a_simple_edit(self):
        original = ["one", "two", "three", "four", "five"]
        hunk = _hunk(2, 1, 2, 1, [("-", "two"), ("+", "TWO")])
        self.assertEqual(
            reconstruct_file_lines(original, [hunk]),
            ["one", "TWO", "three", "four", "five"],
        )

    def test_two_disjoint_hunks_each_apply_independently(self):
        original = [str(i) for i in range(10)]
        first = _hunk(1, 1, 1, 1, [("-", "0"), ("+", "ZERO")])
        second = _hunk(9, 1, 9, 1, [("-", "8"), ("+", "EIGHT")])
        result = reconstruct_file_lines(original, [first, second])
        self.assertEqual(result[0], "ZERO")
        self.assertEqual(result[8], "EIGHT")
        # everything untouched in between is copied through unchanged
        self.assertEqual(result[1:8], original[1:8])

    def test_partial_application_leaves_uncommitted_hunk_ranges_untouched(self):
        original = ["one", "two", "three"]
        only_first = _hunk(1, 1, 1, 1, [("-", "one"), ("+", "ONE")])
        # A second hunk touching "three" exists in the diff but is not
        # passed in here -- as if its patch set hasn't been committed yet.
        result = reconstruct_file_lines(original, [only_first])
        self.assertEqual(result, ["ONE", "two", "three"])

    def test_pure_insertion_does_not_consume_original_lines(self):
        original = ["a", "b"]
        insertion = _hunk(1, 0, 2, 1, [("+", "inserted")])
        result = reconstruct_file_lines(original, [insertion])
        self.assertEqual(result, ["a", "inserted", "b"])

    def test_full_deletion_of_a_file_yields_empty_result(self):
        original = ["only line"]
        deletion = _hunk(1, 1, 0, 0, [("-", "only line")])
        self.assertEqual(reconstruct_file_lines(original, [deletion]), [])

    def test_context_lines_are_preserved_in_the_new_side(self):
        original = ["keep", "change", "keep2"]
        hunk = _hunk(
            1, 3, 1, 3,
            [(" ", "keep"), ("-", "change"), ("+", "CHANGED"), (" ", "keep2")],
        )
        self.assertEqual(
            reconstruct_file_lines(original, [hunk]), ["keep", "CHANGED", "keep2"]
        )


class TestCommitMessage(unittest.TestCase):
    def test_message_includes_patch_set_index_and_files(self):
        hunk = _hunk(1, 1, 1, 1, [("-", "x"), ("+", "y")], file_path="a.py")
        patch_set = PatchSet(index=3, hunks=[hunk])
        self.assertEqual(commit_message(patch_set), "splice: patch set 3 (a.py)")

    def test_message_lists_every_file_in_a_merged_patch_set(self):
        hunk_a = _hunk(1, 1, 1, 1, [("-", "x"), ("+", "y")], file_path="a.py")
        hunk_b = _hunk(1, 1, 1, 1, [("-", "x"), ("+", "y")], file_path="b.py")
        patch_set = PatchSet(index=1, hunks=[hunk_a, hunk_b])
        self.assertEqual(commit_message(patch_set), "splice: patch set 1 (a.py, b.py)")


if __name__ == "__main__":
    unittest.main()
