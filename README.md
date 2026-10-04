# git-splice

A git plugin that slices your messy working-tree diff into a stack of
minimal, independently-applicable commits. It looks at hunk adjacency and
shared identifiers across your changes to figure out which edits actually
belong together, then (in later milestones) shows the proposed stack as an
interactive ASCII dependency graph before writing anything.

## Install

Requires Python 3.9+. No third-party dependencies.

```sh
pip install -e .
```

This installs the `git-splice` command (invokable as `git splice` once it
is on your `PATH`, since git dispatches `git <subcommand>` to any
`git-<subcommand>` executable it finds there).

## Usage

Run it inside a git repository with a working-tree diff:

```sh
git-splice
```

This runs `git diff`, parses it into hunks, builds a graph linking hunks
that are either adjacent in the same file or share a changed identifier,
then greedily clusters connected hunks into independent patch sets and
prints the resulting stack:

```
2 file(s), 3 hunk(s), 2 patch set(s)
patch set 1:
  hunk#0 foo.py @@ -1,4 +1,5 @@
  hunk#1 foo.py @@ -10,3 +11,3 @@
patch set 2:
  hunk#2 bar.py @@ -1,1 +1,2 @@
```

The clustering is deterministic: hunks are visited in a canonical order
(file path, then position in the file, then hunk id) so the same diff
always produces the same patch sets, in the same order, regardless of
dict/set iteration order. See `git_splice/clustering.py` and
`tests/test_clustering.py` for the golden fixtures that pin this down.

Pass `--cached` to inspect the staged diff instead, or one or more paths
to limit the diff (both are forwarded to `git diff`):

```sh
git-splice --cached src/
```

Each patch set is a group of hunks that the shared-identifier/adjacency
analysis believes must travel together. Pass `--graph` to see the same
patch sets rendered as an ASCII boxes-and-arrows dependency graph
instead of the flat hunk listing:

```sh
git-splice --graph
```

```
+-------------------+
| patch set 1       |
| files: a.py, b.py |
| hunks: 3          |
+-------------------+
          |
          v
+-------------------+
| patch set 2       |
| files: c.py       |
| hunks: 1          |
+-------------------+
```

Patch sets are otherwise independent, but two of them can still touch
the same file at different positions; applying them out of order would
shift the context each hunk expects. The graph captures that as an
ordering dependency: an arrow points from the patch set that touches a
shared file earlier to the one that touches it later, labeled with the
file that creates the dependency. If two patch sets disagree about
ordering across different shared files (a cycle), the graph still
renders in a deterministic index-based order and prints a note listing
the conflict instead of failing. See `git_splice/stack_graph.py` and
`git_splice/render.py` for the implementation, and
`tests/test_stack_graph.py` / `tests/test_render.py` for the fixtures
that pin the behavior down.

Before any commit gets written, you can review and rearrange the stack
by hand. Pass `--interactive` (or `-i`) to open an arrow-key terminal UI
over the same patch sets:

```sh
git-splice --interactive
```

```
[up/down: move, m: merge with next, enter/q: confirm]

> patch set 1 (2 hunk(s)) -- a.py, b.py
  patch set 2 (1 hunk(s)) -- c.py
```

Up/down moves the selected patch set, swapping it with its neighbor;
`m` folds the patch set below the selection into the selected one
(hunks from both are re-sorted into canonical file/position order so
the merged result is independent of which side they came from); Enter
or `q` confirms the stack as currently arranged and prints it. Nothing
is written to the repository by this command -- it only decides the
order and grouping that a later milestone will use when creating
commits. The editing rules themselves (`git_splice/interactive.py`'s
`ReorderState` and `handle_key`) are plain, terminal-free Python so
they are covered by `tests/test_interactive.py` without needing a real
TTY; only the thin curses loop that reads actual keypresses requires
one, so `--interactive` needs to run attached to a real terminal.

Turning each patch set into an actual commit lands in a later
milestone.

## Status

This project is built autonomously, milestone by milestone, and every
change is gated on its test suite passing before it is kept. Run the
tests with:

```sh
python -m unittest discover -s tests
```
