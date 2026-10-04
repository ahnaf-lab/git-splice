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
analysis believes must travel together; turning each patch set into an
actual commit, and presenting the stack interactively for review before
writing anything, lands in a later milestone.

## Status

This project is built autonomously, milestone by milestone, and every
change is gated on its test suite passing before it is kept. Run the
tests with:

```sh
python -m unittest discover -s tests
```
