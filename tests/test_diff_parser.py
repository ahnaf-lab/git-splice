import unittest

from git_splice.diff_parser import parse_unified_diff

SIMPLE_DIFF = """\
diff --git a/foo.py b/foo.py
index 83db48f..bf269f4 100644
--- a/foo.py
+++ b/foo.py
@@ -1,4 +1,5 @@
 def greet():
-    print("hi")
+    print("hello")
+    print("world")
     return None
@@ -10,3 +11,3 @@ def other():
 def other():
-    pass
+    return 1
"""

NEW_FILE_DIFF = """\
diff --git a/new.py b/new.py
new file mode 100644
index 0000000..e69de29
--- /dev/null
+++ b/new.py
@@ -0,0 +1,2 @@
+print("a")
+print("b")
"""

RENAME_DIFF = """\
diff --git a/old_name.py b/new_name.py
similarity index 100%
rename from old_name.py
rename to new_name.py
"""


class TestParseUnifiedDiff(unittest.TestCase):
    def test_parses_two_hunks_in_one_file(self):
        file_diffs = parse_unified_diff(SIMPLE_DIFF)
        self.assertEqual(len(file_diffs), 1)
        file_diff = file_diffs[0]
        self.assertEqual(file_diff.path, "foo.py")
        self.assertEqual(len(file_diff.hunks), 2)

    def test_hunk_header_fields_and_body(self):
        file_diff = parse_unified_diff(SIMPLE_DIFF)[0]
        first_hunk = file_diff.hunks[0]
        self.assertEqual(first_hunk.old_start, 1)
        self.assertEqual(first_hunk.old_count, 4)
        self.assertEqual(first_hunk.new_start, 1)
        self.assertEqual(first_hunk.new_count, 5)
        self.assertEqual(first_hunk.added_lines, ['    print("hello")', '    print("world")'])
        self.assertEqual(first_hunk.removed_lines, ['    print("hi")'])
        self.assertIn("    return None", first_hunk.context_lines)

    def test_identifiers_extracted_from_changed_lines_only(self):
        file_diff = parse_unified_diff(SIMPLE_DIFF)[0]
        first_hunk = file_diff.hunks[0]
        self.assertIn("print", first_hunk.identifiers)
        self.assertIn("hello", first_hunk.identifiers)
        # "greet" only appears in a context line, so it should not show up.
        self.assertNotIn("greet", first_hunk.identifiers)

    def test_new_file_diff(self):
        file_diff = parse_unified_diff(NEW_FILE_DIFF)[0]
        self.assertTrue(file_diff.is_new_file)
        self.assertEqual(file_diff.path, "new.py")
        self.assertEqual(len(file_diff.hunks), 1)
        self.assertEqual(file_diff.hunks[0].added_lines, ['print("a")', 'print("b")'])

    def test_rename_diff_with_no_hunks(self):
        file_diff = parse_unified_diff(RENAME_DIFF)[0]
        self.assertTrue(file_diff.is_rename)
        self.assertEqual(file_diff.old_path, "old_name.py")
        self.assertEqual(file_diff.new_path, "new_name.py")
        self.assertEqual(file_diff.hunks, [])

    def test_empty_diff_returns_no_files(self):
        self.assertEqual(parse_unified_diff(""), [])

    def test_hunk_ids_are_unique_across_files(self):
        combined = SIMPLE_DIFF + NEW_FILE_DIFF
        file_diffs = parse_unified_diff(combined)
        all_ids = [hunk.id for fd in file_diffs for hunk in fd.hunks]
        self.assertEqual(len(all_ids), len(set(all_ids)))


if __name__ == "__main__":
    unittest.main()
