"""
Tests for parse_args() — parameter dependency resolution and mutual exclusion.

Covers:
- ARG_IMPLIES: --word / --markdown each imply --extract-elements
- mutually_exclusive_group: --word + --markdown together are rejected
- --extract-elements can be set directly without --word/--markdown
- Unrelated flags are unaffected
"""
import sys
import unittest

from pdf2zh.pdf2zh import ARG_IMPLIES, parse_args


class TestArgImpliesSchema(unittest.TestCase):
    """ARG_IMPLIES table itself is well-formed."""

    def test_word_implies_extract_elements(self):
        self.assertIn("extract_elements", ARG_IMPLIES["word"])

    def test_markdown_implies_extract_elements(self):
        self.assertIn("extract_elements", ARG_IMPLIES["markdown"])


class TestWordImpliesExtractElements(unittest.TestCase):
    def test_word_sets_extract_elements_true(self):
        args = parse_args(["doc.pdf", "--word"])
        self.assertTrue(args.extract_elements)

    def test_word_flag_itself_is_true(self):
        args = parse_args(["doc.pdf", "--word"])
        self.assertTrue(args.word)

    def test_markdown_is_false_when_word_used(self):
        args = parse_args(["doc.pdf", "--word"])
        self.assertFalse(args.markdown)


class TestMarkdownImpliesExtractElements(unittest.TestCase):
    def test_markdown_sets_extract_elements_true(self):
        args = parse_args(["doc.pdf", "--markdown"])
        self.assertTrue(args.extract_elements)

    def test_markdown_flag_itself_is_true(self):
        args = parse_args(["doc.pdf", "--markdown"])
        self.assertTrue(args.markdown)

    def test_word_is_false_when_markdown_used(self):
        args = parse_args(["doc.pdf", "--markdown"])
        self.assertFalse(args.word)


class TestMutualExclusion(unittest.TestCase):
    def test_word_and_markdown_together_raise_system_exit(self):
        with self.assertRaises(SystemExit):
            parse_args(["doc.pdf", "--word", "--markdown"])

    def test_error_code_is_nonzero(self):
        with self.assertRaises(SystemExit) as ctx:
            parse_args(["doc.pdf", "--word", "--markdown"])
        self.assertNotEqual(ctx.exception.code, 0)


class TestNoExportFlag(unittest.TestCase):
    def test_extract_elements_defaults_false(self):
        args = parse_args(["doc.pdf"])
        self.assertFalse(args.extract_elements)

    def test_word_defaults_false(self):
        args = parse_args(["doc.pdf"])
        self.assertFalse(args.word)

    def test_markdown_defaults_false(self):
        args = parse_args(["doc.pdf"])
        self.assertFalse(args.markdown)


class TestExplicitExtractElements(unittest.TestCase):
    """--extract-elements can be used standalone without an export flag."""

    def test_extract_elements_standalone(self):
        args = parse_args(["doc.pdf", "--extract-elements"])
        self.assertTrue(args.extract_elements)
        self.assertFalse(args.word)
        self.assertFalse(args.markdown)


class TestUnrelatedFlagsUnaffected(unittest.TestCase):
    """ARG_IMPLIES resolution must not touch unrelated flags."""

    def test_ignore_cache_unaffected_by_word(self):
        args = parse_args(["doc.pdf", "--word"])
        self.assertFalse(args.ignore_cache)

    def test_ignore_cache_unaffected_by_markdown(self):
        args = parse_args(["doc.pdf", "--markdown"])
        self.assertFalse(args.ignore_cache)


if __name__ == "__main__":
    unittest.main()
