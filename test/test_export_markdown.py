import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch


class TestLoadElementBboxes(unittest.TestCase):
    """_load_element_bboxes should read figures.json and tables.json."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def _write(self, fname, data):
        path = os.path.join(self.tmpdir, fname)
        with open(path, "w") as f:
            json.dump(data, f)

    def test_loads_figures_json(self):
        from pdf2zh.export_markdown import _load_element_bboxes
        self._write("figures.json", [
            {"pageno": 0, "idx": 1, "image_file": "p1_figure_001.png",
             "x0": 10, "y0": 20, "x1": 200, "y1": 300},
        ])
        result = _load_element_bboxes(self.tmpdir)
        self.assertIn(0, result)
        self.assertEqual(len(result[0]), 1)
        self.assertEqual(result[0][0]["image_file"], "p1_figure_001.png")

    def test_loads_tables_json(self):
        from pdf2zh.export_markdown import _load_element_bboxes
        self._write("tables.json", [
            {"pageno": 4, "idx": 1, "image_file": "p5_table_001.png",
             "x0": 50, "y0": 60, "x1": 500, "y1": 250},
        ])
        result = _load_element_bboxes(self.tmpdir)
        self.assertIn(4, result)
        self.assertEqual(result[4][0]["image_file"], "p5_table_001.png")

    def test_merges_figures_and_tables(self):
        from pdf2zh.export_markdown import _load_element_bboxes
        self._write("figures.json", [
            {"pageno": 2, "idx": 1, "image_file": "p3_figure_001.png",
             "x0": 0, "y0": 0, "x1": 100, "y1": 100},
        ])
        self._write("tables.json", [
            {"pageno": 2, "idx": 1, "image_file": "p3_table_001.png",
             "x0": 200, "y0": 200, "x1": 400, "y1": 400},
        ])
        result = _load_element_bboxes(self.tmpdir)
        self.assertEqual(len(result[2]), 2)

    def test_missing_files_return_empty(self):
        from pdf2zh.export_markdown import _load_element_bboxes
        result = _load_element_bboxes(self.tmpdir)
        self.assertEqual(result, {})


class TestBlockOverlapsElement(unittest.TestCase):
    """_block_overlaps_element should detect IoB ≥ threshold."""

    def _b(self, x0, y0, x1, y1):
        return {"x0": x0, "y0": y0, "x1": x1, "y1": y1, "content": "text"}

    def _e(self, x0, y0, x1, y1):
        return {"x0": x0, "y0": y0, "x1": x1, "y1": y1, "pageno": 0}

    def test_full_containment_detected(self):
        from pdf2zh.export_markdown import _block_overlaps_element
        block = self._b(100, 100, 200, 150)   # 100×50 block
        elem  = self._e(50, 50, 300, 300)     # element fully contains block
        self.assertTrue(_block_overlaps_element(block, [elem]))

    def test_no_overlap(self):
        from pdf2zh.export_markdown import _block_overlaps_element
        block = self._b(0, 0, 50, 50)
        elem  = self._e(100, 100, 200, 200)
        self.assertFalse(_block_overlaps_element(block, [elem]))

    def test_partial_overlap_below_threshold(self):
        from pdf2zh.export_markdown import _block_overlaps_element
        # block 100×100, element covers only 20×100 = 20% of block area
        block = self._b(0, 0, 100, 100)
        elem  = self._e(80, 0, 200, 100)     # intersection 20×100 = 20%
        self.assertFalse(_block_overlaps_element(block, [elem]))

    def test_partial_overlap_above_threshold(self):
        from pdf2zh.export_markdown import _block_overlaps_element
        # block 100×100, element covers 60×100 = 60% of block area
        block = self._b(0, 0, 100, 100)
        elem  = self._e(40, 0, 200, 100)     # intersection 60×100 = 60%
        self.assertTrue(_block_overlaps_element(block, [elem]))

    def test_empty_elem_list(self):
        from pdf2zh.export_markdown import _block_overlaps_element
        block = self._b(0, 0, 100, 100)
        self.assertFalse(_block_overlaps_element(block, []))

    def test_integrated_extraction_filter(self):
        """_extract_page_text_blocks drops blocks overlapping elem_bboxes."""
        from pdf2zh.export_markdown import _extract_page_text_blocks
        page = MagicMock()
        page.rect.height = 800
        # Table region covers y=60-250 on this page
        elem_bboxes = [{"x0": 0, "y0": 60, "x1": 600, "y1": 250, "pageno": 0}]
        page.get_text.return_value = [
            (0, 70, 500, 90, "Table row 1", 0, 0),     # fully inside table region
            (0, 300, 500, 320, "Normal paragraph", 1, 0),  # outside
        ]
        result = _extract_page_text_blocks(page, elem_bboxes)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["content"], "Normal paragraph")


class TestNormalizeBlockText(unittest.TestCase):
    """_normalize_block_text should collapse intra-block soft line breaks."""

    def test_uppercase_next_line_joined_with_space(self):
        from pdf2zh.export_markdown import _normalize_block_text
        # Next lines start with uppercase → joined with a space (word boundary)
        text = "End of phrase\nBeginning of next\nAnd another"
        self.assertEqual(
            _normalize_block_text(text),
            "End of phrase Beginning of next And another",
        )

    def test_lowercase_next_line_glued_directly(self):
        from pdf2zh.export_markdown import _normalize_block_text
        # Next line starts with lowercase ASCII → glue directly (mid-word split)
        # e.g. "Quac\nkenbush" within the same block
        text = "This is propos\nition of the theory"
        self.assertEqual(
            _normalize_block_text(text),
            "This is proposition of the theory",
        )

    def test_hyphenated_break_glued(self):
        from pdf2zh.export_markdown import _normalize_block_text
        # "meth-\nod" → "method"
        text = "The meth-\nod is applied"
        self.assertEqual(_normalize_block_text(text), "The method is applied")

    def test_cjk_lines_joined_without_space(self):
        from pdf2zh.export_markdown import _normalize_block_text
        # Chinese characters: no space should be inserted
        text = "这是一段\n很长的中文\n句子"
        self.assertEqual(_normalize_block_text(text), "这是一段很长的中文句子")

    def test_single_line_unchanged(self):
        from pdf2zh.export_markdown import _normalize_block_text
        text = "No newlines here"
        self.assertEqual(_normalize_block_text(text), "No newlines here")

    def test_empty_string(self):
        from pdf2zh.export_markdown import _normalize_block_text
        self.assertEqual(_normalize_block_text(""), "")

    def test_trailing_newline_stripped_context(self):
        """After strip(), trailing newline is gone; normalization handles the rest."""
        from pdf2zh.export_markdown import _normalize_block_text
        # strip() is applied before _normalize_block_text in the pipeline,
        # but test that a trailing \n line (empty) doesn't add a trailing space
        text = "Line one\nLine two"
        result = _normalize_block_text(text)
        self.assertFalse(result.endswith(" "))

    def test_mixed_english_and_cjk(self):
        from pdf2zh.export_markdown import _normalize_block_text
        # CJK ending → no space; then English continues
        text = "实验结果表明\nthe accuracy is high"
        result = _normalize_block_text(text)
        # CJK line ends → joined directly
        self.assertEqual(result, "实验结果表明the accuracy is high")

    def test_intra_block_mid_word_glued(self):
        from pdf2zh.export_markdown import _normalize_block_text
        # "Quac\nkenbush" should become "Quackenbush" (no space)
        text = "（Quac\nkenbush，2018）"
        self.assertEqual(_normalize_block_text(text), "（Quackenbush，2018）")

    def test_new_sentence_after_period_gets_space(self):
        from pdf2zh.export_markdown import _normalize_block_text
        # Next line starts uppercase → join with space
        text = "End of sentence.\nNew sentence here."
        self.assertEqual(_normalize_block_text(text), "End of sentence. New sentence here.")

    def test_year_split_glued(self):
        from pdf2zh.export_markdown import _normalize_block_text
        # "20\n17" → "2017"
        text = "（Radhakrishnan 等，20\n17）"
        self.assertEqual(_normalize_block_text(text), "（Radhakrishnan 等，2017）")

    def test_thousands_separator_glued(self):
        from pdf2zh.export_markdown import _normalize_block_text
        # "12\n,850" → "12,850"
        text = "共 12\n,850 种期刊"
        self.assertEqual(_normalize_block_text(text), "共 12,850 种期刊")

    def test_digit_before_uppercase_not_glued(self):
        from pdf2zh.export_markdown import _normalize_block_text
        # "10\nFlow theory" is a table row → keep space
        text = "10\nFlow theory"
        self.assertEqual(_normalize_block_text(text), "10 Flow theory")

    def test_allcaps_abbreviation_glued(self):
        from pdf2zh.export_markdown import _normalize_block_text
        # "SL\nR" → "SLR"
        text = "We used SL\nR in our review"
        self.assertEqual(_normalize_block_text(text), "We used SLR in our review")

    def test_allcaps_abbreviation_unctad(self):
        from pdf2zh.export_markdown import _normalize_block_text
        # "UNC\nTAD" → "UNCTAD"
        text = "data from UNC\nTAD database"
        self.assertEqual(_normalize_block_text(text), "data from UNCTAD database")

    def test_mixed_case_word_not_glued_as_abbreviation(self):
        from pdf2zh.export_markdown import _normalize_block_text
        # "United States\nOf" → "United States Of" (last word "States" not all-caps)
        text = "United States\nOf America"
        self.assertEqual(_normalize_block_text(text), "United States Of America")


class TestMergeBrokenLines(unittest.TestCase):
    """_merge_broken_lines should join soft-wrapped English mid-word splits."""

    def _b(self, text, x0=0, y0=0, x1=100, y1=20):
        return {"x0": x0, "y0": y0, "x1": x1, "y1": y1, "content": text}

    def test_mid_word_split_merged(self):
        """'Quac' + 'kenbush,' → 'Quackenbush,'"""
        from pdf2zh.export_markdown import _merge_broken_lines
        blocks = [self._b("（Quac"), self._b("kenbush，")]
        result = _merge_broken_lines(blocks)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["content"], "（Quackenbush，")

    def test_sentence_end_not_merged(self):
        """Block ending with '.' starts a new paragraph."""
        from pdf2zh.export_markdown import _merge_broken_lines
        blocks = [self._b("First sentence."), self._b("second sentence")]
        result = _merge_broken_lines(blocks)
        self.assertEqual(len(result), 2)

    def test_uppercase_start_not_merged(self):
        """Block starting with uppercase is a new sentence."""
        from pdf2zh.export_markdown import _merge_broken_lines
        blocks = [self._b("End of para"), self._b("New paragraph here")]
        result = _merge_broken_lines(blocks)
        self.assertEqual(len(result), 2)

    def test_cjk_not_merged(self):
        """Chinese blocks are never merged by this rule."""
        from pdf2zh.export_markdown import _merge_broken_lines
        blocks = [self._b("这是第一段"), self._b("继续内容")]
        result = _merge_broken_lines(blocks)
        self.assertEqual(len(result), 2)

    def test_multiple_consecutive_splits_merged(self):
        """A word split across three blocks is fully reconstructed."""
        from pdf2zh.export_markdown import _merge_broken_lines
        blocks = [self._b("pro"), self._b("posi"), self._b("tion")]
        result = _merge_broken_lines(blocks)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["content"], "proposition")

    def test_empty_list(self):
        from pdf2zh.export_markdown import _merge_broken_lines
        self.assertEqual(_merge_broken_lines([]), [])

    def test_single_block_unchanged(self):
        from pdf2zh.export_markdown import _merge_broken_lines
        blocks = [self._b("Only one block")]
        result = _merge_broken_lines(blocks)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["content"], "Only one block")


class TestIsVerticalTextBlock(unittest.TestCase):
    """_is_vertical_text_block should detect per-character-line blocks."""

    def test_doi_watermark_detected(self):
        from pdf2zh.export_markdown import _is_vertical_text_block
        # Simulate ' \n1\n5\n2\n0\n6\n7\n9\n3\n,\n ...' — each char on own line
        text = "\n".join(list("1520679,2022,4,D")) + "\n"
        self.assertTrue(_is_vertical_text_block(text))

    def test_normal_paragraph_not_detected(self):
        from pdf2zh.export_markdown import _is_vertical_text_block
        text = "This is a normal paragraph.\nIt has two long lines.\n"
        self.assertFalse(_is_vertical_text_block(text))

    def test_short_block_not_detected(self):
        from pdf2zh.export_markdown import _is_vertical_text_block
        # Fewer than 5 lines → not classified as vertical text
        text = "A\nB\nC\n"
        self.assertFalse(_is_vertical_text_block(text))

    def test_mixed_block_not_detected(self):
        from pdf2zh.export_markdown import _is_vertical_text_block
        # Some short lines but avg > 2 → not vertical text
        text = "A\nB\nThis is longer\nD\nE\n"
        self.assertFalse(_is_vertical_text_block(text))

    def test_vertical_block_filtered_in_extraction(self):
        """_extract_page_text_blocks drops vertical-text blocks."""
        from pdf2zh.export_markdown import _extract_page_text_blocks
        vertical_text = "\n".join(list("Downloaded from https://example")) + "\n"
        page = MagicMock()
        page.rect.height = 800
        page.get_text.return_value = [
            (0, 5, 400, 700, vertical_text, 0, 0),  # vertical watermark
            (0, 200, 400, 400, "Normal body paragraph", 1, 0),
        ]
        result = _extract_page_text_blocks(page)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["content"], "Normal body paragraph")


class TestIsHeaderFooter(unittest.TestCase):
    """_is_header_footer should detect blocks in page margin zones."""

    def _block(self, y0, y1):
        return {"x0": 0, "y0": y0, "x1": 100, "y1": y1, "content": "text"}

    def test_header_block_detected(self):
        from pdf2zh.export_markdown import _is_header_footer
        # block fully inside top 8% of 800pt page → y1 < 64
        self.assertTrue(_is_header_footer(self._block(10, 30), page_height=800))

    def test_footer_block_detected(self):
        from pdf2zh.export_markdown import _is_header_footer
        # block starts in bottom 8% of 800pt page → y0 > 736
        self.assertTrue(_is_header_footer(self._block(750, 780), page_height=800))

    def test_body_block_not_filtered(self):
        from pdf2zh.export_markdown import _is_header_footer
        # block in middle of page
        self.assertFalse(_is_header_footer(self._block(200, 230), page_height=800))

    def test_custom_margin(self):
        from pdf2zh.export_markdown import _is_header_footer
        # with 5% margin on 1000pt page, threshold is 50pt / 950pt
        self.assertTrue(_is_header_footer(self._block(0, 45), page_height=1000, margin=0.05))
        self.assertFalse(_is_header_footer(self._block(0, 55), page_height=1000, margin=0.05))

    def test_header_filter_integrated(self):
        """_extract_page_text_blocks should drop header/footer blocks."""
        from pdf2zh.export_markdown import _extract_page_text_blocks
        page = MagicMock()
        page.rect.height = 800
        page.get_text.return_value = [
            (0, 5, 200, 30, "Page header", 0, 0),    # y1=30 < 64 → header
            (0, 100, 400, 200, "Body content", 1, 0), # body
            (0, 760, 200, 790, "Page 12", 2, 0),      # y0=760 > 736 → footer
        ]
        result = _extract_page_text_blocks(page)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["content"], "Body content")


class TestExtractPageTextBlocks(unittest.TestCase):
    """_extract_page_text_blocks should drop single-character and margin blocks."""

    PAGE_HEIGHT = 800

    def _make_page(self, raw_blocks):
        """Return a mock pymupdf.Page whose get_text('blocks') returns raw_blocks.

        page.rect.height is set to PAGE_HEIGHT so _is_header_footer can compare
        block coordinates against a real number.
        """
        page = MagicMock()
        page.rect.height = self.PAGE_HEIGHT
        page.get_text.return_value = raw_blocks
        return page

    def test_normal_blocks_kept(self):
        from pdf2zh.export_markdown import _extract_page_text_blocks
        # Blocks placed in the middle of the page (y in 100–700 of 800pt)
        page = self._make_page([
            (0, 100, 100, 120, "Hello world", 0, 0),
            (0, 200, 100, 220, "Second paragraph", 1, 0),
        ])
        result = _extract_page_text_blocks(page)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["content"], "Hello world")

    def test_single_char_block_discarded(self):
        from pdf2zh.export_markdown import _extract_page_text_blocks
        page = self._make_page([
            (0, 100, 5, 110, "A", 0, 0),   # single char — vertical text artefact
            (0, 110, 5, 120, "|", 1, 0),   # pipe separator — also single char
            (0, 200, 100, 400, "Real paragraph", 2, 0),
        ])
        result = _extract_page_text_blocks(page)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["content"], "Real paragraph")

    def test_empty_block_discarded(self):
        from pdf2zh.export_markdown import _extract_page_text_blocks
        page = self._make_page([
            (0, 100, 100, 120, "   ", 0, 0),  # whitespace only
            (0, 200, 100, 400, "Content", 1, 0),
        ])
        result = _extract_page_text_blocks(page)
        self.assertEqual(len(result), 1)

    def test_two_char_block_kept(self):
        from pdf2zh.export_markdown import _extract_page_text_blocks
        page = self._make_page([
            (0, 200, 20, 210, "OK", 0, 0),
        ])
        result = _extract_page_text_blocks(page)
        self.assertEqual(len(result), 1)


class TestParseElemFilename(unittest.TestCase):
    def test_figure_filename(self):
        from pdf2zh.export_markdown import _parse_elem_filename
        self.assertEqual(
            _parse_elem_filename("p2_figure_001.png"),
            {"type": "figure", "idx": 1},
        )

    def test_table_filename(self):
        from pdf2zh.export_markdown import _parse_elem_filename
        self.assertEqual(
            _parse_elem_filename("p10_table_003.png"),
            {"type": "table", "idx": 3},
        )

    def test_invalid_filename_returns_none(self):
        from pdf2zh.export_markdown import _parse_elem_filename
        self.assertIsNone(_parse_elem_filename("invalid.png"))
        self.assertIsNone(_parse_elem_filename("figure_001.png"))


class TestMakeCaptionLabel(unittest.TestCase):
    def test_figure_label(self):
        from pdf2zh.export_markdown import _make_caption_label
        self.assertEqual(_make_caption_label("p1_figure_001.png"), "Figure 1")

    def test_table_label(self):
        from pdf2zh.export_markdown import _make_caption_label
        self.assertEqual(_make_caption_label("p3_table_002.png"), "Table 2")

    def test_unknown_type_capitalized(self):
        from pdf2zh.export_markdown import _make_caption_label
        self.assertEqual(_make_caption_label("p1_chart_001.png"), "Chart 1")

    def test_invalid_filename_fallback(self):
        from pdf2zh.export_markdown import _make_caption_label
        self.assertEqual(_make_caption_label("weird.png"), "weird")


class TestIsCaption(unittest.TestCase):
    def test_figure_keyword(self):
        from pdf2zh.export_markdown import _is_caption
        self.assertTrue(_is_caption("Figure 1 shows the results"))
        self.assertTrue(_is_caption("fig. 2 comparison"))

    def test_table_keyword(self):
        from pdf2zh.export_markdown import _is_caption
        self.assertTrue(_is_caption("Table 3 summary statistics"))

    def test_cjk_caption(self):
        from pdf2zh.export_markdown import _is_caption
        self.assertTrue(_is_caption("图1 实验结果"))
        self.assertTrue(_is_caption("表2 数据统计"))

    def test_long_text_not_caption(self):
        from pdf2zh.export_markdown import _is_caption
        self.assertFalse(_is_caption("figure " + "x" * 295))

    def test_period_ending_not_caption(self):
        from pdf2zh.export_markdown import _is_caption
        self.assertFalse(_is_caption("This figure shows the result."))

    def test_body_text_without_keywords(self):
        from pdf2zh.export_markdown import _is_caption
        self.assertFalse(_is_caption("The proposed method achieves state-of-the-art"))


import os
import shutil
import tempfile


class TestExportPdfToMarkdown(unittest.TestCase):
    PDF_PLAIN = os.path.join(
        os.path.dirname(__file__), "file", "translate.cli.plain.text.pdf"
    )
    PDF_FIGURE = os.path.join(
        os.path.dirname(__file__), "file", "translate.cli.text.with.figure.pdf"
    )

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _fake_elem_dir(self, filenames):
        """Create a temp elem_dir with stub PNG files."""
        elem_dir = os.path.join(self.tmpdir, "elems")
        elements = os.path.join(elem_dir, "elements")
        os.makedirs(elements)
        for fname in filenames:
            with open(os.path.join(elements, fname), "wb") as f:
                # Minimal 1x1 PNG (67 bytes)
                f.write(
                    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
                    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
                    b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18"
                    b"\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
                )
        return elem_dir

    def test_creates_md_file(self):
        from pdf2zh.export_markdown import export_pdf_to_markdown
        output_dir = os.path.join(self.tmpdir, "out")
        md_path = export_pdf_to_markdown(self.PDF_PLAIN, None, output_dir)
        self.assertTrue(os.path.isfile(md_path))
        self.assertTrue(md_path.endswith(".md"))

    def test_creates_images_directory(self):
        from pdf2zh.export_markdown import export_pdf_to_markdown
        output_dir = os.path.join(self.tmpdir, "out")
        export_pdf_to_markdown(self.PDF_PLAIN, None, output_dir)
        self.assertTrue(os.path.isdir(os.path.join(output_dir, "images")))

    def test_copies_images_to_images_dir(self):
        from pdf2zh.export_markdown import export_pdf_to_markdown
        elem_dir = self._fake_elem_dir(["p1_figure_001.png"])
        output_dir = os.path.join(self.tmpdir, "out")
        export_pdf_to_markdown(self.PDF_PLAIN, elem_dir, output_dir)
        self.assertTrue(
            os.path.isfile(os.path.join(output_dir, "images", "p1_figure_001.png"))
        )

    def test_image_wikilink_appears_in_markdown(self):
        from pdf2zh.export_markdown import export_pdf_to_markdown
        elem_dir = self._fake_elem_dir(["p1_figure_001.png"])
        output_dir = os.path.join(self.tmpdir, "out")
        md_path = export_pdf_to_markdown(self.PDF_PLAIN, elem_dir, output_dir)
        content = open(md_path, encoding="utf-8").read()
        self.assertIn("![[images/p1_figure_001.png]]", content)

    def test_page_separator_for_multipage_pdf(self):
        import pymupdf
        from pdf2zh.export_markdown import export_pdf_to_markdown
        doc = pymupdf.open(self.PDF_PLAIN)
        page_count = doc.page_count
        doc.close()
        if page_count < 2:
            self.skipTest("PDF has only one page; separator test requires 2+")
        output_dir = os.path.join(self.tmpdir, "out")
        md_path = export_pdf_to_markdown(self.PDF_PLAIN, None, output_dir)
        content = open(md_path, encoding="utf-8").read()
        self.assertIn("\n---\n", content)

    def test_no_separator_on_first_page(self):
        from pdf2zh.export_markdown import export_pdf_to_markdown
        output_dir = os.path.join(self.tmpdir, "out")
        md_path = export_pdf_to_markdown(self.PDF_PLAIN, None, output_dir)
        content = open(md_path, encoding="utf-8").read()
        self.assertFalse(content.startswith("---"))


class TestTranslateToMarkdownSignature(unittest.TestCase):
    def test_function_exists_and_is_callable(self):
        from pdf2zh.high_level import translate_to_markdown
        import inspect
        sig = inspect.signature(translate_to_markdown)
        self.assertIn("files", sig.parameters)
        self.assertIn("output", sig.parameters)
        self.assertIn("lang_out", sig.parameters)


class TestMarkdownCliFlag(unittest.TestCase):
    def test_markdown_flag_is_registered(self):
        from pdf2zh.pdf2zh import create_parser
        parser = create_parser()
        args = parser.parse_args(["dummy.pdf", "--markdown"])
        self.assertTrue(args.markdown)

    def test_markdown_flag_defaults_false(self):
        from pdf2zh.pdf2zh import create_parser
        parser = create_parser()
        args = parser.parse_args(["dummy.pdf"])
        self.assertFalse(args.markdown)


if __name__ == "__main__":
    unittest.main()
