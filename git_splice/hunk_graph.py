"""Build an adjacency graph over hunks from shared files/lines/identifiers.

Two hunks are linked (and therefore belong together in the eventual commit
stack) when either:

* they sit in the same file with only a small gap of unchanged lines
  between them ("adjacent-lines"), or
* they touch at least one identical identifier token, in any file
  ("shared-identifier:<name>").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Set

from .diff_parser import FileDiff, Hunk

# Default max gap (in new-file line numbers) between two hunks in the same
# file for them to still be considered adjacent.
DEFAULT_LINE_ADJACENCY = 3


@dataclass
class HunkGraph:
    hunks: List[Hunk]
    edges: Dict[int, Dict[int, Set[str]]] = field(default_factory=dict)

    @classmethod
    def build(
        cls,
        file_diffs: List[FileDiff],
        line_adjacency: int = DEFAULT_LINE_ADJACENCY,
    ) -> "HunkGraph":
        hunks = [hunk for file_diff in file_diffs for hunk in file_diff.hunks]
        graph = cls(hunks=hunks)
        for hunk in hunks:
            graph.edges.setdefault(hunk.id, {})

        graph._link_adjacent_hunks(line_adjacency)
        graph._link_shared_identifiers()
        return graph

    def _link_adjacent_hunks(self, line_adjacency: int) -> None:
        by_file: Dict[str, List[Hunk]] = {}
        for hunk in self.hunks:
            by_file.setdefault(hunk.file_path, []).append(hunk)

        for file_hunks in by_file.values():
            file_hunks.sort(key=lambda h: h.new_start)
            for earlier, later in zip(file_hunks, file_hunks[1:]):
                gap = later.new_start - (earlier.new_start + earlier.new_count)
                if gap <= line_adjacency:
                    self._add_edge(earlier.id, later.id, "adjacent-lines")

    def _link_shared_identifiers(self) -> None:
        ident_to_hunk_ids: Dict[str, List[int]] = {}
        for hunk in self.hunks:
            for identifier in hunk.identifiers:
                ident_to_hunk_ids.setdefault(identifier, []).append(hunk.id)

        for identifier, hunk_ids in ident_to_hunk_ids.items():
            for i in range(len(hunk_ids)):
                for j in range(i + 1, len(hunk_ids)):
                    self._add_edge(
                        hunk_ids[i], hunk_ids[j], f"shared-identifier:{identifier}"
                    )

    def _add_edge(self, a: int, b: int, reason: str) -> None:
        if a == b:
            return
        self.edges.setdefault(a, {}).setdefault(b, set()).add(reason)
        self.edges.setdefault(b, {}).setdefault(a, set()).add(reason)

    def neighbors(self, hunk_id: int) -> Dict[int, Set[str]]:
        return self.edges.get(hunk_id, {})

    def connected_components(self) -> List[Set[int]]:
        """Group hunk ids into clusters that must stay in the same commit."""
        seen: Set[int] = set()
        components: List[Set[int]] = []

        for hunk in self.hunks:
            if hunk.id in seen:
                continue
            stack = [hunk.id]
            component: Set[int] = set()
            while stack:
                current = stack.pop()
                if current in component:
                    continue
                component.add(current)
                seen.add(current)
                for neighbor_id in self.edges.get(current, {}):
                    if neighbor_id not in component:
                        stack.append(neighbor_id)
            components.append(component)

        return components
