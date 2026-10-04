"""Interactive stack editor: merge/reorder patch sets before anything is written.

`ReorderState` holds the editable stack (current patch-set order plus a
cursor) and the handful of operations a reviewer needs -- move the
selected patch set up or down, or merge it with the one below. It is
plain Python with no curses dependency, so the editing rules can be
unit-tested without a real terminal.

`handle_key` maps a single keypress to a `ReorderState` operation and is
also terminal-agnostic: it only reads integer key codes (curses key
constants or ASCII), so tests can drive it directly. `run_interactive`
is the thin curses loop that a real session uses to collect those key
codes from the keyboard and redraw the screen; it is not covered by
unit tests since it requires a real TTY, but it is exercised by
`cli.py` and kept intentionally small.
"""

from __future__ import annotations

import curses
from dataclasses import dataclass
from typing import List, Tuple

from .clustering import PatchSet
from .diff_parser import Hunk


def _hunk_sort_key(hunk: Hunk) -> Tuple[str, int, int]:
    return (hunk.file_path, hunk.new_start, hunk.id)


@dataclass
class ReorderState:
    """Mutable editing state for a stack of patch sets.

    `order` lists the current patch sets top-to-bottom. `cursor` is the
    index into `order` of the currently selected patch set. Every
    operation leaves `cursor` pointing at the patch set the reviewer was
    just looking at (or the merged result), so repeated keypresses
    behave predictably instead of the selection jumping around.
    """

    order: List[PatchSet]
    cursor: int = 0

    def __post_init__(self) -> None:
        if not self.order:
            raise ValueError("ReorderState requires at least one patch set")
        self.cursor = max(0, min(self.cursor, len(self.order) - 1))

    @property
    def selected(self) -> PatchSet:
        return self.order[self.cursor]

    def move_up(self) -> bool:
        """Swap the selected patch set with the one above it.

        Returns whether anything moved (false at the top of the stack).
        """
        if self.cursor == 0:
            return False
        above = self.cursor - 1
        self.order[above], self.order[self.cursor] = (
            self.order[self.cursor],
            self.order[above],
        )
        self.cursor = above
        self._renumber()
        return True

    def move_down(self) -> bool:
        """Swap the selected patch set with the one below it.

        Returns whether anything moved (false at the bottom of the stack).
        """
        if self.cursor >= len(self.order) - 1:
            return False
        below = self.cursor + 1
        self.order[below], self.order[self.cursor] = (
            self.order[self.cursor],
            self.order[below],
        )
        self.cursor = below
        self._renumber()
        return True

    def merge_with_next(self) -> bool:
        """Fold the patch set below the selection into the selected one.

        The merged hunks are re-sorted into canonical order so the
        result is identical regardless of which side they came from.
        Returns whether a merge happened (false if the selection is
        already the last patch set).
        """
        if self.cursor >= len(self.order) - 1:
            return False
        first = self.order[self.cursor]
        second = self.order.pop(self.cursor + 1)
        merged_hunks = sorted(first.hunks + second.hunks, key=_hunk_sort_key)
        self.order[self.cursor] = PatchSet(index=first.index, hunks=merged_hunks)
        self._renumber()
        return True

    def _renumber(self) -> None:
        for position, patch_set in enumerate(self.order, start=1):
            patch_set.index = position


# Keys that confirm the stack and end the session.
_CONFIRM_KEYS = {ord("\n"), ord("\r"), curses.KEY_ENTER, ord("q"), ord("Q")}
_UP_KEYS = {curses.KEY_UP, ord("k")}
_DOWN_KEYS = {curses.KEY_DOWN, ord("j")}
_MERGE_KEYS = {ord("m"), ord("M")}


def handle_key(state: ReorderState, key: int) -> Tuple[bool, str]:
    """Apply one keypress to `state`.

    Returns `(keep_running, status_message)`. `keep_running` is false
    once the reviewer has confirmed the stack (Enter or `q`); the
    caller should stop reading keys and use `state.order` as the result.
    """
    if key in _UP_KEYS:
        return True, "moved up" if state.move_up() else "already at top"
    if key in _DOWN_KEYS:
        return True, "moved down" if state.move_down() else "already at bottom"
    if key in _MERGE_KEYS:
        return True, "merged with next" if state.merge_with_next() else "nothing below to merge"
    if key in _CONFIRM_KEYS:
        return False, "confirmed"
    return True, ""


def _status_line(message: str) -> str:
    return f"[up/down: move, m: merge with next, enter/q: confirm]  {message}".rstrip()


def _render_lines(state: ReorderState, message: str) -> List[str]:
    lines = [_status_line(message), ""]
    for position, patch_set in enumerate(state.order):
        marker = ">" if position == state.cursor else " "
        files = ", ".join(patch_set.files)
        lines.append(
            f"{marker} patch set {patch_set.index} "
            f"({len(patch_set.hunks)} hunk(s)) -- {files}"
        )
    return lines


def _interactive_loop(screen, patch_sets: List[PatchSet]) -> List[PatchSet]:
    curses.curs_set(0)
    state = ReorderState(order=list(patch_sets))
    message = ""

    while True:
        screen.erase()
        for row, line in enumerate(_render_lines(state, message)):
            try:
                screen.addstr(row, 0, line)
            except curses.error:
                pass
        screen.refresh()

        key = screen.getch()
        keep_running, message = handle_key(state, key)
        if not keep_running:
            break

    return state.order


def run_interactive(patch_sets: List[PatchSet]) -> List[PatchSet]:
    """Drive `_interactive_loop` inside a real terminal via curses.

    Returns the patch sets in whatever order the reviewer left them,
    with merges already applied. Raises whatever `curses.wrapper` raises
    if the current terminal cannot support curses (e.g. no TTY).
    """
    return curses.wrapper(lambda screen: _interactive_loop(screen, patch_sets))
