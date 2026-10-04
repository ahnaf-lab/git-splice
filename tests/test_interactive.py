import curses
import unittest

from git_splice.clustering import PatchSet
from git_splice.diff_parser import Hunk
from git_splice.interactive import ReorderState, handle_key


def _hunk(id_: int, file_path: str, new_start: int) -> Hunk:
    return Hunk(
        id=id_,
        file_path=file_path,
        old_start=new_start,
        old_count=1,
        new_start=new_start,
        new_count=1,
        section_heading="",
    )


def _patch_set(index: int, file_path: str, new_start: int) -> PatchSet:
    return PatchSet(index=index, hunks=[_hunk(index, file_path, new_start)])


class TestReorderStateMoves(unittest.TestCase):
    def setUp(self):
        self.state = ReorderState(
            order=[
                _patch_set(1, "a.py", 1),
                _patch_set(2, "b.py", 1),
                _patch_set(3, "c.py", 1),
            ]
        )

    def test_move_down_swaps_with_next_and_follows_cursor(self):
        moved = self.state.move_down()
        self.assertTrue(moved)
        self.assertEqual([ps.files[0] for ps in self.state.order], ["b.py", "a.py", "c.py"])
        self.assertEqual(self.state.cursor, 1)

    def test_move_up_swaps_with_previous_and_follows_cursor(self):
        self.state.cursor = 2
        moved = self.state.move_up()
        self.assertTrue(moved)
        self.assertEqual([ps.files[0] for ps in self.state.order], ["a.py", "c.py", "b.py"])
        self.assertEqual(self.state.cursor, 1)

    def test_move_up_at_top_is_a_no_op(self):
        moved = self.state.move_up()
        self.assertFalse(moved)
        self.assertEqual([ps.files[0] for ps in self.state.order], ["a.py", "b.py", "c.py"])

    def test_move_down_at_bottom_is_a_no_op(self):
        self.state.cursor = 2
        moved = self.state.move_down()
        self.assertFalse(moved)
        self.assertEqual(self.state.cursor, 2)

    def test_moves_renumber_patch_sets_to_match_new_positions(self):
        self.state.move_down()
        self.assertEqual([ps.index for ps in self.state.order], [1, 2, 3])


class TestReorderStateMerge(unittest.TestCase):
    def test_merge_with_next_combines_hunks_into_one_patch_set(self):
        state = ReorderState(order=[_patch_set(1, "a.py", 1), _patch_set(2, "a.py", 10)])
        merged = state.merge_with_next()
        self.assertTrue(merged)
        self.assertEqual(len(state.order), 1)
        self.assertEqual(len(state.order[0].hunks), 2)

    def test_merge_with_next_sorts_hunks_canonically_regardless_of_input_order(self):
        later = _patch_set(1, "a.py", 10)
        earlier = _patch_set(2, "a.py", 1)
        state = ReorderState(order=[later, earlier])
        state.merge_with_next()
        self.assertEqual([h.new_start for h in state.order[0].hunks], [1, 10])

    def test_merge_at_bottom_of_stack_is_a_no_op(self):
        state = ReorderState(order=[_patch_set(1, "a.py", 1), _patch_set(2, "b.py", 1)])
        state.cursor = 1
        merged = state.merge_with_next()
        self.assertFalse(merged)
        self.assertEqual(len(state.order), 2)

    def test_merge_renumbers_remaining_patch_sets_sequentially(self):
        state = ReorderState(
            order=[
                _patch_set(1, "a.py", 1),
                _patch_set(2, "b.py", 1),
                _patch_set(3, "c.py", 1),
            ]
        )
        state.merge_with_next()
        self.assertEqual([ps.index for ps in state.order], [1, 2])


class TestReorderStateConstruction(unittest.TestCase):
    def test_empty_order_is_rejected(self):
        with self.assertRaises(ValueError):
            ReorderState(order=[])

    def test_out_of_range_cursor_is_clamped(self):
        state = ReorderState(order=[_patch_set(1, "a.py", 1)], cursor=5)
        self.assertEqual(state.cursor, 0)


class TestHandleKey(unittest.TestCase):
    def setUp(self):
        self.state = ReorderState(
            order=[_patch_set(1, "a.py", 1), _patch_set(2, "b.py", 1)]
        )

    def test_down_key_moves_selection_and_keeps_session_running(self):
        keep_running, message = handle_key(self.state, curses.KEY_DOWN)
        self.assertTrue(keep_running)
        self.assertEqual(self.state.cursor, 1)
        self.assertIn("moved down", message)

    def test_merge_key_merges_and_keeps_session_running(self):
        keep_running, _ = handle_key(self.state, ord("m"))
        self.assertTrue(keep_running)
        self.assertEqual(len(self.state.order), 1)

    def test_quit_key_ends_the_session(self):
        keep_running, message = handle_key(self.state, ord("q"))
        self.assertFalse(keep_running)
        self.assertEqual(message, "confirmed")

    def test_unknown_key_is_ignored_and_session_keeps_running(self):
        keep_running, message = handle_key(self.state, ord("z"))
        self.assertTrue(keep_running)
        self.assertEqual(message, "")
        self.assertEqual(self.state.cursor, 0)


if __name__ == "__main__":
    unittest.main()
