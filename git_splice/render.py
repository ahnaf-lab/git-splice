"""Render a patch-set stack as a boxes-and-arrows ASCII graph.

Each patch set becomes a box listing its files and hunk count. Boxes
are stacked top to bottom in dependency order (see `stack_graph`). A
plain vertical arrow is drawn between two consecutive boxes when one
depends directly on the other; dependencies that reach further back in
the stack are called out as a text line inside the dependent box
instead, since a pure-text renderer can't route an arrow around boxes
it has already drawn.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from .clustering import PatchSet
from .stack_graph import StackEdge, compute_stack_edges, topological_order


def _box_lines(patch_set: PatchSet, skip_edges: List[StackEdge]) -> List[str]:
    lines = [
        f"patch set {patch_set.index}",
        f"files: {', '.join(patch_set.files)}",
        f"hunks: {len(patch_set.hunks)}",
    ]
    for edge in skip_edges:
        files = ", ".join(edge.files)
        lines.append(f"also depends on patch set {edge.before} ({files})")
    return lines


def _draw_box(lines: List[str], width: int) -> List[str]:
    border = "+" + "-" * (width + 2) + "+"
    body = [f"| {line.ljust(width)} |" for line in lines]
    return [border, *body, border]


def render_stack(patch_sets: List[PatchSet], edges: List[StackEdge] = None) -> str:
    """Render `patch_sets` as a top-to-bottom ASCII dependency graph."""
    if not patch_sets:
        return "No patch sets to render."

    if edges is None:
        edges = compute_stack_edges(patch_sets)

    order, conflicting_edges = topological_order(patch_sets, edges)
    conflicting_pairs = {(edge.before, edge.after) for edge in conflicting_edges}

    by_index: Dict[int, PatchSet] = {ps.index: ps for ps in patch_sets}
    direct_edge_into: Dict[int, StackEdge] = {}
    skip_edges_into: Dict[int, List[StackEdge]] = {index: [] for index in order}

    position = {index: pos for pos, index in enumerate(order)}
    for edge in edges:
        if (edge.before, edge.after) in conflicting_pairs:
            continue
        if position[edge.after] == position[edge.before] + 1:
            direct_edge_into[edge.after] = edge
        else:
            skip_edges_into[edge.after].append(edge)

    boxes: List[Tuple[int, List[str]]] = [
        (index, _box_lines(by_index[index], skip_edges_into[index])) for index in order
    ]
    content_width = max(
        len(line) for _, lines in boxes for line in lines
    )

    rendered: List[str] = []
    for position_index, (index, lines) in enumerate(boxes):
        if position_index > 0:
            prev_index = order[position_index - 1]
            edge = direct_edge_into.get(index)
            if edge is not None and edge.before == prev_index:
                files = ", ".join(edge.files)
                rendered.append("|".center(content_width + 4))
                rendered.append(f"v ({files})".center(content_width + 4))
            else:
                rendered.append("|".center(content_width + 4))
                rendered.append("v".center(content_width + 4))
        rendered.extend(_draw_box(lines, content_width))

    if conflicting_edges:
        rendered.append("")
        rendered.append("note: ordering conflicts could not be fully resolved:")
        for edge in conflicting_edges:
            files = ", ".join(edge.files)
            rendered.append(
                f"  patch set {edge.before} and patch set {edge.after} "
                f"disagree on order via {files}"
            )

    return "\n".join(rendered)
