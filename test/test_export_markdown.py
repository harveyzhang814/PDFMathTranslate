import unittest


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


if __name__ == "__main__":
    unittest.main()
