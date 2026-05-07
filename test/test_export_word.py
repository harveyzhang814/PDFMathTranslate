import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch, call


class TestExportPdfToWord(unittest.TestCase):
    """Tests for export_pdf_to_word in pdf2zh/export_word.py."""

    def _make_mock_page(self, blocks, width=612.0, height=792.0):
        """Return a mock pymupdf Page with the given text blocks."""
        page = MagicMock()
        page.rect.width = width
        page.rect.height = height
        # get_text("blocks") returns tuples (x0,y0,x1,y1,text,...)
        page.get_text.return_value = [
            (b["x0"], b["y0"], b["x1"], b["y1"], b["content"], 0, 0)
            for b in blocks
        ]
        return page

    @patch("pdf2zh.export_word.sort_text_blocks_by_layout")
    @patch("pymupdf.open")
    def test_sort_result_is_used(self, mock_pymupdf_open, mock_sort):
        """Bug fix: sort_text_blocks_by_layout return value must be assigned back."""
        blocks_in = [
            {"x0": 300.0, "y0": 100.0, "x1": 580.0, "y1": 120.0, "content": "Right col"},
            {"x0": 50.0,  "y0": 100.0, "x1": 280.0, "y1": 120.0, "content": "Left col"},
        ]
        sorted_blocks = [
            {"x0": 50.0,  "y0": 100.0, "x1": 280.0, "y1": 120.0, "content": "Left col"},
            {"x0": 300.0, "y0": 100.0, "x1": 580.0, "y1": 120.0, "content": "Right col"},
        ]
        mock_sort.return_value = sorted_blocks

        mock_doc = MagicMock()
        mock_page = self._make_mock_page(blocks_in)
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))
        mock_pymupdf_open.return_value = mock_doc

        from docx import Document as RealDocument
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            out_path = f.name
        try:
            from pdf2zh.export_word import export_pdf_to_word
            export_pdf_to_word("fake.pdf", None, out_path)

            # sort was called
            mock_sort.assert_called_once()
            # Verify by inspecting what was written to the real docx
            doc = RealDocument(out_path)
            paras = [p.text for p in doc.paragraphs if p.text.strip()]
            # "Left col" must appear before "Right col"
            self.assertIn("Left col", paras)
            self.assertIn("Right col", paras)
            self.assertLess(paras.index("Left col"), paras.index("Right col"))
        finally:
            os.unlink(out_path)

    @patch("pymupdf.open")
    def test_empty_page_does_not_abort_subsequent_pages(self, mock_pymupdf_open):
        """Bug fix: empty-text page must use continue, not return, so later pages are kept."""
        page_empty = self._make_mock_page([])
        page_text  = self._make_mock_page([
            {"x0": 50.0, "y0": 200.0, "x1": 500.0, "y1": 220.0, "content": "Hello world"},
        ])

        mock_doc = MagicMock()
        mock_doc.__iter__ = MagicMock(return_value=iter([page_empty, page_text]))
        mock_pymupdf_open.return_value = mock_doc

        from docx import Document as RealDocument
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            out_path = f.name
        try:
            from pdf2zh.export_word import export_pdf_to_word
            export_pdf_to_word("fake.pdf", None, out_path)

            doc = RealDocument(out_path)
            paras = [p.text for p in doc.paragraphs if p.text.strip()]
            # "Hello world" from page 2 must be present
            self.assertIn("Hello world", paras)
        finally:
            os.unlink(out_path)

    @patch("pymupdf.open")
    def test_three_pages_all_processed(self, mock_pymupdf_open):
        """All pages in a multi-page document are written to the output."""
        pages = [
            self._make_mock_page([{"x0": 50.0, "y0": 100.0, "x1": 500.0, "y1": 120.0, "content": f"Page {i} text"}])
            for i in range(1, 4)
        ]
        mock_doc = MagicMock()
        mock_doc.__iter__ = MagicMock(return_value=iter(pages))
        mock_pymupdf_open.return_value = mock_doc

        from docx import Document as RealDocument
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            out_path = f.name
        try:
            from pdf2zh.export_word import export_pdf_to_word
            export_pdf_to_word("fake.pdf", None, out_path)

            doc = RealDocument(out_path)
            paras = [p.text for p in doc.paragraphs if p.text.strip()]
            for i in range(1, 4):
                self.assertIn(f"Page {i} text", paras)
        finally:
            os.unlink(out_path)


if __name__ == "__main__":
    unittest.main()
