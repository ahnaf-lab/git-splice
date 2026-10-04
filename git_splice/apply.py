"""Apply a patch-set stack as a real sequence of commits.

`--apply` turns the proposed stack (see `clustering`, `stack_graph`) into
an actual chain of commits on top of HEAD, one per patch set, each
containing exactly that patch set's hunks and nothing else. It never
touches the working tree: every intermediate tree is built with git's
plumbing commands (`hash-object`, `update-index`, `write-tree`,
`commit-tree`) against a throwaway index file, and only once every
commit in the chain exists do we move the branch ref and refresh the
real index (never the working tree) to match the new HEAD.

Reconstructing the content a commit should have for a file is a pure
function of that file's pristine (HEAD) content and the subset of hunks
committed so far: hunks never overlap (two overlapping hunks would have
been linked by `hunk_graph`'s adjacent-lines edge and ended up in the
same patch set), so lines outside every committed hunk's range are
copied through unchanged and lines inside a committed hunk's range are
replaced by that hunk's "new side" (context and added lines, in order).
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from .clustering import PatchSet
from .diff_parser import FileDiff, Hunk

_FILE_MODE = "100644"
_EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


class ApplyError(RuntimeError):
    """Raised when `--apply` cannot safely build or write the commit chain."""


@dataclass(frozen=True)
class CommitRecord:
    """One commit written by `apply_patch_sets`."""

    sha: str
    message: str
    patch_set_index: int


def reconstruct_file_lines(original_lines: List[str], hunks: List[Hunk]) -> List[str]:
    """Rebuild a file's lines from its pristine content and committed hunks.

    `hunks` must all belong to the same file and have non-overlapping
    `old_start`/`old_count` ranges. Any stretch of `original_lines` not
    covered by one of `hunks` is copied through unchanged; each hunk's
    own range is replaced by its "new side" -- context and added lines,
    in their original relative order.
    """
    ordered = sorted(hunks, key=lambda h: h.old_start)
    result: List[str] = []
    cursor = 0
    for hunk in ordered:
        start = hunk.old_start - 1 if hunk.old_count else hunk.old_start
        result.extend(original_lines[cursor:start])
        result.extend(text for tag, text in hunk.body_lines if tag in (" ", "+"))
        cursor = start + hunk.old_count
    result.extend(original_lines[cursor:])
    return result


def commit_message(patch_set: PatchSet) -> str:
    """The deterministic commit message for one patch set."""
    return f"splice: patch set {patch_set.index} ({', '.join(patch_set.files)})"


def _run(args: List[str], env: Optional[Dict[str, str]] = None, input_text: Optional[str] = None) -> str:
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        shell=False,
        check=False,
        env=env,
        input=input_text,
    )
    if result.returncode != 0:
        raise ApplyError(f"`{' '.join(args)}` failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _current_head() -> Optional[str]:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        capture_output=True,
        text=True,
        shell=False,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _symbolic_head_ref() -> Optional[str]:
    result = subprocess.run(
        ["git", "symbolic-ref", "-q", "HEAD"],
        capture_output=True,
        text=True,
        shell=False,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _read_blob_lines(ref: str, path: str) -> List[str]:
    """Read `path` as of `ref`, split into lines without their terminators.

    Returns `[]` if the path does not exist at `ref` (a new file).
    """
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        capture_output=True,
        text=True,
        shell=False,
        check=False,
    )
    if result.returncode != 0:
        return []
    return result.stdout.splitlines()


def _check_preconditions(cached: bool, head: Optional[str]) -> None:
    if cached or head is None:
        return
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        shell=False,
        check=False,
    )
    if result.returncode != 0:
        raise ApplyError(
            "refusing to apply: the index has staged changes beyond HEAD -- "
            "commit or unstage them before running --apply on the working-tree diff"
        )


def _hash_object(content: str, env: Dict[str, str]) -> str:
    return _run(["git", "hash-object", "-w", "--stdin"], env=env, input_text=content)


def apply_patch_sets(
    patch_sets: List[PatchSet], file_diffs: List[FileDiff], cached: bool = False
) -> List[CommitRecord]:
    """Write `patch_sets`, in the given order, as a chain of commits on HEAD.

    Every intermediate tree is built against a throwaway index file --
    the repository's real index and working tree are left untouched
    until the whole chain exists, at which point the branch ref (or bare
    HEAD, if detached) is moved and the real index is refreshed to match
    the new HEAD via `git reset --mixed` (which never touches working
    tree files). Returns one `CommitRecord` per patch set, in commit
    order.
    """
    if not patch_sets:
        return []

    head = _current_head()
    _check_preconditions(cached, head)

    file_diff_by_path: Dict[str, FileDiff] = {fd.path: fd for fd in file_diffs}
    deleted_files: Set[str] = {
        path for path, fd in file_diff_by_path.items() if fd.is_deleted_file
    }
    original_lines_by_file: Dict[str, List[str]] = {}
    for path, file_diff in file_diff_by_path.items():
        if file_diff.is_new_file or head is None:
            original_lines_by_file[path] = []
        else:
            original_lines_by_file[path] = _read_blob_lines(head, path)

    committed_hunks_by_file: Dict[str, List[Hunk]] = {}
    records: List[CommitRecord] = []

    with tempfile.TemporaryDirectory(prefix="git-splice-index-") as tmp_dir:
        env = dict(os.environ)
        env["GIT_INDEX_FILE"] = os.path.join(tmp_dir, "index")

        if head is not None:
            _run(["git", "read-tree", head], env=env)
        else:
            _run(["git", "read-tree", "--empty"], env=env)

        parent = head
        for patch_set in patch_sets:
            touched_files: Set[str] = set()
            for hunk in patch_set.hunks:
                committed_hunks_by_file.setdefault(hunk.file_path, []).append(hunk)
                touched_files.add(hunk.file_path)

            for path in sorted(touched_files):
                new_lines = reconstruct_file_lines(
                    original_lines_by_file.get(path, []), committed_hunks_by_file[path]
                )
                if not new_lines and path in deleted_files:
                    _run(["git", "update-index", "--force-remove", path], env=env)
                    continue
                content = "\n".join(new_lines) + ("\n" if new_lines else "")
                blob_sha = _hash_object(content, env)
                _run(
                    [
                        "git",
                        "update-index",
                        "--add",
                        "--cacheinfo",
                        f"{_FILE_MODE},{blob_sha},{path}",
                    ],
                    env=env,
                )

            tree_sha = _run(["git", "write-tree"], env=env)
            commit_args = ["git", "commit-tree", tree_sha]
            if parent is not None:
                commit_args += ["-p", parent]
            message = commit_message(patch_set)
            commit_sha = _run(commit_args + ["-m", message], env=env)

            parent = commit_sha
            records.append(
                CommitRecord(sha=commit_sha, message=message, patch_set_index=patch_set.index)
            )

    final_sha = parent
    branch_ref = _symbolic_head_ref()
    ref_to_move = branch_ref or "HEAD"
    update_ref_args = ["git", "update-ref", ref_to_move, final_sha]
    if head is not None:
        update_ref_args.append(head)
    _run(update_ref_args)
    _run(["git", "reset", "--mixed"])

    return records
