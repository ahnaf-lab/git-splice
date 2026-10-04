"""Deterministic greedy clustering of hunks into independent patch sets.

The hunk-adjacency graph (see `hunk_graph`) tells us which hunks *must*
travel together: anything reachable via an "adjacent-lines" or
"shared-identifier" edge belongs in the same patch set. What it does not
pin down is an ordering -- dict and set iteration order in CPython is
insertion-order dependent, so two runs over the same diff could in
principle group or list hunks differently depending on how the graph was
built in memory.

This module greedily merges hunks into patch sets while visiting them in
a canonical order (file path, then position in the new file, then hunk
id), so the output depends only on the diff's own content. That
determinism is what makes golden tests against fixture diffs possible:
the same fixture always produces the same patch-set layout, byte for
byte.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from .diff_parser import Hunk
from .hunk_graph import HunkGraph


def _sort_key(hunk: Hunk) -> Tuple[str, int, int]:
    return (hunk.file_path, hunk.new_start, hunk.id)


@dataclass
class PatchSet:
    """An independent group of hunks that belong in the same commit."""

    index: int
    hunks: List[Hunk]

    @property
    def files(self) -> List[str]:
        return sorted({hunk.file_path for hunk in self.hunks})

    @property
    def hunk_ids(self) -> List[int]:
        return [hunk.id for hunk in self.hunks]


class _UnionFind:
    """Union-find with a deterministic tie-break (lowest id wins as root)."""

    def __init__(self, ids: List[int]):
        self._parent = {i: i for i in ids}

    def find(self, x: int) -> int:
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]
            x = self._parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        root_a, root_b = self.find(a), self.find(b)
        if root_a == root_b:
            return
        if root_a < root_b:
            self._parent[root_b] = root_a
        else:
            self._parent[root_a] = root_b


def cluster_hunks(graph: HunkGraph) -> List[PatchSet]:
    """Greedily merge hunks into independent, deterministically ordered patch sets.

    Hunks are visited in canonical order (file path, then position in the
    new file, then id) and unioned with every graph neighbor in that same
    canonical order. The resulting patch sets -- and the hunk order within
    each one -- depend only on the diff's content, never on hash/dict
    iteration order.
    """
    ordered_hunks = sorted(graph.hunks, key=_sort_key)
    union_find = _UnionFind([hunk.id for hunk in ordered_hunks])

    for hunk in ordered_hunks:
        for neighbor_id in sorted(graph.neighbors(hunk.id)):
            union_find.union(hunk.id, neighbor_id)

    groups: Dict[int, List[Hunk]] = {}
    for hunk in ordered_hunks:
        root = union_find.find(hunk.id)
        groups.setdefault(root, []).append(hunk)

    grouped_hunks = list(groups.values())
    for hunks in grouped_hunks:
        hunks.sort(key=_sort_key)
    grouped_hunks.sort(key=lambda hunks: _sort_key(hunks[0]))

    return [
        PatchSet(index=index, hunks=hunks)
        for index, hunks in enumerate(grouped_hunks, start=1)
    ]
