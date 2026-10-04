"""Command-line entry point for `git splice`.

This milestone only wires up enough CLI to be useful for inspection: it
runs `git diff` in the current repository, parses the result, builds the
hunk adjacency graph, and prints a summary of the hunks and the clusters
they fall into. The interactive dependency graph and commit-writing
behaviour described in the project README land in later milestones.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from typing import List, Optional

from .diff_parser import parse_unified_diff
from .hunk_graph import HunkGraph


def _run_git_diff(extra_args: List[str]) -> str:
    command = ["git", "diff"] + extra_args
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        shell=False,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git diff failed: {result.stderr.strip()}")
    return result.stdout


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="git-splice",
        description="Inspect the hunk adjacency graph for the current working-tree diff.",
    )
    parser.add_argument(
        "--cached",
        action="store_true",
        help="Inspect the staged diff instead of the working-tree diff.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Limit the diff to these paths (passed through to git diff).",
    )
    return parser


def summarize(diff_text: str) -> str:
    file_diffs = parse_unified_diff(diff_text)
    graph = HunkGraph.build(file_diffs)
    components = graph.connected_components()

    lines = []
    total_hunks = len(graph.hunks)
    lines.append(f"{len(file_diffs)} file(s), {total_hunks} hunk(s), {len(components)} cluster(s)")

    hunks_by_id = {hunk.id: hunk for hunk in graph.hunks}
    for index, component in enumerate(components, start=1):
        ordered = sorted(component)
        lines.append(f"cluster {index}:")
        for hunk_id in ordered:
            hunk = hunks_by_id[hunk_id]
            lines.append(
                f"  hunk#{hunk.id} {hunk.file_path} "
                f"@@ -{hunk.old_start},{hunk.old_count} +{hunk.new_start},{hunk.new_count} @@"
            )
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    extra_args = list(args.paths)
    if args.cached:
        extra_args = ["--cached"] + extra_args

    try:
        diff_text = _run_git_diff(extra_args)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if not diff_text.strip():
        print("No changes found.")
        return 0

    print(summarize(diff_text))
    return 0


if __name__ == "__main__":
    sys.exit(main())
