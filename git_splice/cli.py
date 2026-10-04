"""Command-line entry point for `git splice`.

This milestone wires up enough CLI to be useful for inspection: it runs
`git diff` in the current repository, parses the result, builds the
hunk adjacency graph, greedily clusters hunks into independent patch
sets, and prints the resulting stack -- either as a one-line-per-hunk
summary, as an ASCII boxes-and-arrows dependency graph (`--graph`), or
by first letting the user merge/reorder the patch sets in an arrow-key
terminal UI (`--interactive`) before printing the result. Commit-writing
lands in a later milestone.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from typing import List, Optional

from .clustering import cluster_hunks
from .diff_parser import parse_unified_diff
from .hunk_graph import HunkGraph
from .interactive import run_interactive
from .render import render_stack


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
        "--graph",
        action="store_true",
        help="Print the proposed stack as an ASCII boxes-and-arrows graph.",
    )
    parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help=(
            "Review the proposed stack in an arrow-key terminal UI before "
            "printing it: up/down moves the selection, 'm' merges it with "
            "the patch set below, and Enter or 'q' confirms."
        ),
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
    patch_sets = cluster_hunks(graph)

    lines = []
    total_hunks = len(graph.hunks)
    lines.append(
        f"{len(file_diffs)} file(s), {total_hunks} hunk(s), {len(patch_sets)} patch set(s)"
    )

    for patch_set in patch_sets:
        lines.append(f"patch set {patch_set.index}:")
        for hunk in patch_set.hunks:
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

    if args.interactive:
        file_diffs = parse_unified_diff(diff_text)
        graph = HunkGraph.build(file_diffs)
        patch_sets = cluster_hunks(graph)
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            print(
                "--interactive requires an interactive terminal (no TTY attached).",
                file=sys.stderr,
            )
            return 1
        patch_sets = run_interactive(patch_sets)
        print(render_stack(patch_sets))
    elif args.graph:
        file_diffs = parse_unified_diff(diff_text)
        graph = HunkGraph.build(file_diffs)
        patch_sets = cluster_hunks(graph)
        print(render_stack(patch_sets))
    else:
        print(summarize(diff_text))
    return 0


if __name__ == "__main__":
    sys.exit(main())
