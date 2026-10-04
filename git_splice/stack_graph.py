"""Order patch sets into a stack and expose their ordering dependencies.

`clustering.cluster_hunks` produces patch sets that are *content*
independent: no two patch sets share a hunk-graph edge. But two patch
sets can still touch the same file at different positions. Applying
them out of position order would move a later patch set's hunks past
context it expects, so for display purposes we treat "patch set A
touches file F earlier than patch set B" as an ordering dependency:
A should be committed before B.

This module computes those dependencies and arranges patch sets into a
single deterministic stack order. Most diffs never touch the same file
from two different patch sets, so most stacks have no edges at all;
the overwhelming common case is just the clustering order already
being a valid stack.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from .clustering import PatchSet


@dataclass(frozen=True)
class StackEdge:
    """An ordering dependency: `before` must be committed ahead of `after`."""

    before: int
    after: int
    files: Tuple[str, ...]


def _min_new_start(patch_set: PatchSet, file_path: str) -> int:
    return min(hunk.new_start for hunk in patch_set.hunks if hunk.file_path == file_path)


def compute_stack_edges(patch_sets: List[PatchSet]) -> List[StackEdge]:
    """Derive ordering edges from patch sets that share a file.

    For each file touched by more than one patch set, the patch sets
    are ranked by their earliest hunk position in that file and a
    dependency is recorded between each consecutive pair. Edges that
    name the same (before, after) pair for multiple files are merged
    into a single edge listing every shared file.
    """
    patch_sets_by_file: Dict[str, List[PatchSet]] = {}
    for patch_set in patch_sets:
        for file_path in patch_set.files:
            patch_sets_by_file.setdefault(file_path, []).append(patch_set)

    pair_to_files: Dict[Tuple[int, int], List[str]] = {}
    for file_path, sharing_sets in patch_sets_by_file.items():
        if len(sharing_sets) < 2:
            continue
        ordered = sorted(
            sharing_sets, key=lambda ps: (_min_new_start(ps, file_path), ps.index)
        )
        for before, after in zip(ordered, ordered[1:]):
            pair_to_files.setdefault((before.index, after.index), []).append(file_path)

    edges = [
        StackEdge(before=before, after=after, files=tuple(sorted(files)))
        for (before, after), files in pair_to_files.items()
    ]
    edges.sort(key=lambda edge: (edge.before, edge.after))
    return edges


def topological_order(
    patch_sets: List[PatchSet], edges: List[StackEdge]
) -> Tuple[List[int], List[StackEdge]]:
    """Order patch set indices so every edge points forward.

    Returns `(order, conflicting_edges)`. `order` always contains every
    patch set index exactly once -- ties (and, if a cycle exists,
    whatever edges couldn't be honored) break by ascending index so the
    result is deterministic. `conflicting_edges` lists edges that point
    backward in the returned order, which can only happen if the
    dependencies themselves form a cycle (e.g. two patch sets each
    touch a different shared file first).
    """
    indices = [patch_set.index for patch_set in patch_sets]
    successors: Dict[int, List[int]] = {index: [] for index in indices}
    in_degree: Dict[int, int] = {index: 0 for index in indices}
    for edge in edges:
        successors[edge.before].append(edge.after)
        in_degree[edge.after] += 1

    ready = sorted(index for index, degree in in_degree.items() if degree == 0)
    order: List[int] = []
    remaining_in_degree = dict(in_degree)

    while ready:
        ready.sort()
        current = ready.pop(0)
        order.append(current)
        for successor in successors[current]:
            remaining_in_degree[successor] -= 1
            if remaining_in_degree[successor] == 0:
                ready.append(successor)

    if len(order) < len(indices):
        # A cycle exists; append whatever is left in deterministic index
        # order so every patch set still appears exactly once.
        remaining = sorted(set(indices) - set(order))
        order.extend(remaining)

    position = {index: position for position, index in enumerate(order)}
    conflicting_edges = [
        edge for edge in edges if position[edge.before] > position[edge.after]
    ]
    return order, conflicting_edges
