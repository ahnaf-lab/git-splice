"""Parse unified diff text (as produced by `git diff`) into structured hunks.

Only the subset of the unified diff format that `git diff` emits is
supported: per-file `diff --git` headers, `---`/`+++` path lines, `@@`
hunk headers, and body lines prefixed with ' ', '+', or '-'. Binary file
diffs are recorded but carry no hunks.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field
from typing import List, Optional, Set, Tuple

_DIFF_GIT_RE = re.compile(r"^diff --git a/(.*) b/(.*)$")
_HUNK_HEADER_RE = re.compile(
    r"^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))? "
    r"\+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@(?P<section>.*)$"
)
_OLD_PATH_RE = re.compile(r"^--- (?:a/(.*)|/dev/null)$")
_NEW_PATH_RE = re.compile(r"^\+\+\+ (?:b/(.*)|/dev/null)$")
_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

# Identifiers shorter than this are too common (loop counters, etc.) to be
# useful signal for "these hunks touch the same thing".
_MIN_IDENTIFIER_LEN = 2

_id_counter = itertools.count()


@dataclass
class Hunk:
    """A single `@@ ... @@` block, plus the file it belongs to."""

    id: int
    file_path: str
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    section_heading: str
    body_lines: List[Tuple[str, str]] = field(default_factory=list)

    @property
    def added_lines(self) -> List[str]:
        return [text for tag, text in self.body_lines if tag == "+"]

    @property
    def removed_lines(self) -> List[str]:
        return [text for tag, text in self.body_lines if tag == "-"]

    @property
    def context_lines(self) -> List[str]:
        return [text for tag, text in self.body_lines if tag == " "]

    @property
    def identifiers(self) -> Set[str]:
        """Identifier-like tokens found in the lines this hunk changed."""
        idents: Set[str] = set()
        for text in self.added_lines + self.removed_lines:
            for match in _IDENTIFIER_RE.finditer(text):
                token = match.group(0)
                if len(token) >= _MIN_IDENTIFIER_LEN:
                    idents.add(token)
        return idents


@dataclass
class FileDiff:
    """All hunks belonging to one file entry in the diff."""

    old_path: Optional[str]
    new_path: Optional[str]
    is_new_file: bool = False
    is_deleted_file: bool = False
    is_rename: bool = False
    is_binary: bool = False
    hunks: List[Hunk] = field(default_factory=list)

    @property
    def path(self) -> str:
        """The path to display/key this file by (new path, or old if deleted)."""
        return self.new_path or self.old_path or "<unknown>"


def _parse_hunk_header(line: str) -> Optional[Tuple[int, int, int, int, str]]:
    match = _HUNK_HEADER_RE.match(line)
    if not match:
        return None
    old_start = int(match.group("old_start"))
    old_count = int(match.group("old_count") or "1")
    new_start = int(match.group("new_start"))
    new_count = int(match.group("new_count") or "1")
    section = match.group("section").strip()
    return old_start, old_count, new_start, new_count, section


def _split_file_sections(lines: List[str]) -> List[List[str]]:
    sections: List[List[str]] = []
    current: List[str] = []
    for line in lines:
        if line.startswith("diff --git "):
            if current:
                sections.append(current)
            current = [line]
        elif current:
            current.append(line)
    if current:
        sections.append(current)
    return sections


def _parse_file_section(lines: List[str]) -> FileDiff:
    header_match = _DIFF_GIT_RE.match(lines[0])
    fallback_old = header_match.group(1) if header_match else None
    fallback_new = header_match.group(2) if header_match else None

    file_diff = FileDiff(old_path=fallback_old, new_path=fallback_new)

    i = 1
    while i < len(lines):
        line = lines[i]
        if line.startswith("new file mode"):
            file_diff.is_new_file = True
        elif line.startswith("deleted file mode"):
            file_diff.is_deleted_file = True
        elif line.startswith("rename from "):
            file_diff.is_rename = True
            file_diff.old_path = line[len("rename from "):]
        elif line.startswith("rename to "):
            file_diff.is_rename = True
            file_diff.new_path = line[len("rename to "):]
        elif line.startswith("Binary files ") or line.startswith("GIT binary patch"):
            file_diff.is_binary = True
        elif line.startswith("--- "):
            old_match = _OLD_PATH_RE.match(line)
            if old_match and old_match.group(1):
                file_diff.old_path = old_match.group(1)
            elif line.strip() == "--- /dev/null":
                file_diff.old_path = None
        elif line.startswith("+++ "):
            new_match = _NEW_PATH_RE.match(line)
            if new_match and new_match.group(1):
                file_diff.new_path = new_match.group(1)
            elif line.strip() == "+++ /dev/null":
                file_diff.new_path = None
        elif line.startswith("@@"):
            parsed = _parse_hunk_header(line)
            if parsed is None:
                i += 1
                continue
            old_start, old_count, new_start, new_count, section = parsed
            hunk = Hunk(
                id=next(_id_counter),
                file_path=file_diff.path,
                old_start=old_start,
                old_count=old_count,
                new_start=new_start,
                new_count=new_count,
                section_heading=section,
            )
            i += 1
            while i < len(lines) and not lines[i].startswith("@@") and not lines[i].startswith("diff --git "):
                body_line = lines[i]
                if body_line.startswith(("+", "-", " ")):
                    hunk.body_lines.append((body_line[0], body_line[1:]))
                elif body_line.startswith("\\ No newline at end of file"):
                    pass
                else:
                    break
                i += 1
            file_diff.hunks.append(hunk)
            continue
        i += 1

    for hunk in file_diff.hunks:
        hunk.file_path = file_diff.path

    return file_diff


def parse_unified_diff(text: str) -> List[FileDiff]:
    """Parse the full output of `git diff` into a list of FileDiff objects."""
    if not text.strip():
        return []
    lines = text.splitlines()
    sections = _split_file_sections(lines)
    return [_parse_file_section(section) for section in sections]
