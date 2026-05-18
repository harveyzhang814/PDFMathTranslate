import json
import os
import tempfile
import unittest

from pdf2zh.caption_pairing import pair_figure_caption, build_element_manifest


class TestPairFigureCaption(unittest.TestCase):

    def test_caption_below_figure_is_paired(self):
        """Caption directly below a figure should be matched to it."""
        figures = [{"x0": 50.0, "y0": 100.0, "x1": 400.0, "y1": 300.0, "idx": 1, "pageno": 0}]
        captions = [{"x0": 80.0, "y0": 305.0, "x1": 380.0, "y1": 325.0, "text": "Figure 1: Example.", "pageno": 0}]
        result = pair_figure_caption(figures, captions)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["caption"], "Figure 1: Example.")

    def test_caption_above_figure_is_paired(self):
        """Caption directly above a figure should also be matched."""
        figures = [{"x0": 50.0, "y0": 200.0, "x1": 400.0, "y1": 400.0, "idx": 1, "pageno": 0}]
        captions = [{"x0": 60.0, "y0": 180.0, "x1": 390.0, "y1": 198.0, "text": "Table caption", "pageno": 0}]
        result = pair_figure_caption(figures, captions)
        self.assertEqual(result[0]["caption"], "Table caption")

    def test_far_caption_not_paired(self):
        """Caption more than 120 px away should not be matched."""
        figures = [{"x0": 50.0, "y0": 100.0, "x1": 400.0, "y1": 300.0, "idx": 1, "pageno": 0}]
        captions = [{"x0": 50.0, "y0": 500.0, "x1": 400.0, "y1": 520.0, "text": "Far caption", "pageno": 0}]
        result = pair_figure_caption(figures, captions)
        self.assertEqual(result[0]["caption"], "")

    def test_caption_on_different_page_not_paired(self):
        figures = [{"x0": 50.0, "y0": 100.0, "x1": 400.0, "y1": 300.0, "idx": 1, "pageno": 0}]
        captions = [{"x0": 50.0, "y0": 305.0, "x1": 400.0, "y1": 325.0, "text": "Other page", "pageno": 1}]
        result = pair_figure_caption(figures, captions)
        self.assertEqual(result[0]["caption"], "")

    def test_each_caption_used_at_most_once(self):
        """Two figures sharing one caption: only the closer one gets it."""
        figures = [
            {"x0": 50.0, "y0": 100.0, "x1": 400.0, "y1": 300.0, "idx": 1, "pageno": 0},
            {"x0": 50.0, "y0": 400.0, "x1": 400.0, "y1": 600.0, "idx": 2, "pageno": 0},
        ]
        # Caption sits just below figure 1 (gap=5) and just above figure 2 (gap=95)
        captions = [{"x0": 50.0, "y0": 305.0, "x1": 400.0, "y1": 325.0, "text": "Only caption", "pageno": 0}]
        result = pair_figure_caption(figures, captions)
        # figure 1 is closer (gap 5 vs 75), so it gets the caption
        self.assertEqual(result[0]["caption"], "Only caption")
        self.assertEqual(result[1]["caption"], "")

    def test_image_ref_format(self):
        figures = [{"x0": 0.0, "y0": 0.0, "x1": 100.0, "y1": 100.0, "idx": 3, "pageno": 1}]
        result = pair_figure_caption(figures, [])
        self.assertEqual(result[0]["image_ref"], "p2_figure_003.png")
        self.assertEqual(result[0]["page"], 2)

    def test_no_figures(self):
        result = pair_figure_caption([], [{"x0": 0.0, "y0": 0.0, "x1": 100.0, "y1": 20.0, "text": "cap", "pageno": 0}])
        self.assertEqual(result, [])

    def test_no_captions(self):
        figures = [{"x0": 50.0, "y0": 100.0, "x1": 400.0, "y1": 300.0, "idx": 1, "pageno": 0}]
        result = pair_figure_caption(figures, [])
        self.assertEqual(result[0]["caption"], "")


class TestBuildElementManifest(unittest.TestCase):

    def test_manifest_written_correctly(self):
        pairings = [
            {"idx": 1, "page": 1, "image_ref": "p1_figure_001.png", "caption": "Fig 1", "fig_bbox": {}},
            {"idx": 2, "page": 1, "image_ref": "p1_figure_002.png", "caption": "", "fig_bbox": {}},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = build_element_manifest(pairings, tmpdir)
            self.assertTrue(os.path.exists(path))
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data["total_figures"], 2)
            self.assertEqual(data["elements"][0]["caption"], "Fig 1")


if __name__ == "__main__":
    unittest.main()
