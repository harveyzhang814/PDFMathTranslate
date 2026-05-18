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


if __name__ == "__main__":
    unittest.main()
