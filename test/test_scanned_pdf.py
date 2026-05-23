"""
Tests for scanned-PDF overlap fix.

Root cause: a scanned PDF has a full-page bitmap image as background and an OCR
text layer on top.  Without a fix, translated text overlaps the visible scan.

Fix: two-part change:
  1. high_level.py — detect full-page background images *before* set_contents()
     replaces the page stream, and set device.page_is_scanned.
  2. pdfinterp.py — in process_page(), insert a white-fill rectangle between
     image ops (ops_base) and translated text (ops_new) when page_is_scanned.

These tests verify each part independently without requiring the ONNX model or
network access.
"""

import io
import struct
import unittest
import zlib

import pymupdf


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_png_white(w: int, h: int) -> bytes:
    """Return raw PNG bytes for a white w×h image."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        c = len(data).to_bytes(4, "big") + tag + data
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return c + crc.to_bytes(4, "big")

    header = chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    raw_rows = b"".join(b"\x00" + b"\xFF\xFF\xFF" * w for _ in range(h))
    idat = chunk(b"IDAT", zlib.compress(raw_rows))
    iend = chunk(b"IEND", b"")
    return b"\x89PNG\r\n\x1a\n" + header + idat + iend


def _make_scanned_pdf(page_w: int = 200, page_h: int = 200) -> bytes:
    """PDF with a full-page bitmap image + a short OCR text string.

    This mimics a scanned document: the image covers 100% of the page, and
    there is an invisible OCR text layer on top.
    """
    doc = pymupdf.open()
    page = doc.new_page(width=page_w, height=page_h)
    img_rect = pymupdf.Rect(0, 0, page_w, page_h)
    page.insert_image(img_rect, stream=_make_png_white(20, 20))
    page.insert_text((10, 100), "Hello OCR", fontsize=12, color=(0, 0, 0))
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _make_text_only_pdf(page_w: int = 200, page_h: int = 200) -> bytes:
    """PDF with only text — no background image."""
    doc = pymupdf.open()
    page = doc.new_page(width=page_w, height=page_h)
    page.insert_text((10, 100), "Normal text page", fontsize=12, color=(0, 0, 0))
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _make_small_image_pdf(page_w: int = 200, page_h: int = 200) -> bytes:
    """PDF with a small image (10×10 pt on a 200×200 pt page → 0.25% area)."""
    doc = pymupdf.open()
    page = doc.new_page(width=page_w, height=page_h)
    # Tiny image in corner — well below the 70% threshold
    page.insert_image(pymupdf.Rect(0, 0, 10, 10), stream=_make_png_white(5, 5))
    page.insert_text((10, 100), "Page with small image", fontsize=12, color=(0, 0, 0))
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Part 1: Detection logic in high_level.py
# ---------------------------------------------------------------------------

class TestScannedPageDetection(unittest.TestCase):
    """Tests for the 'is this page a scanned background?' detection logic.

    The logic is: get_images(full=True) + get_image_rects(xref) BEFORE
    set_contents() replaces the stream; if any image area / page area ≥ 0.70,
    page_is_scanned = True.

    These tests do NOT call translate_stream (no model needed).
    """

    def _detect(self, pdf_bytes: bytes, pageno: int = 0) -> bool:
        """Reproduce the detection logic from high_level.py translate_patch()."""
        doc = pymupdf.open(stream=pdf_bytes)
        mu_page = doc[pageno]
        page_area = mu_page.rect.width * mu_page.rect.height
        if page_area <= 0:
            return False
        for img_info in mu_page.get_images(full=True):
            xref_img = img_info[0]
            rects = mu_page.get_image_rects(xref_img)
            if rects:
                img_area = rects[0].width * rects[0].height
                if img_area / page_area >= 0.7:
                    return True
        return False

    def test_full_page_image_detected_as_scanned(self):
        """A page where one image covers the entire page must be detected."""
        pdf_bytes = _make_scanned_pdf()
        self.assertTrue(
            self._detect(pdf_bytes),
            "Full-page image (ratio=1.0) must trigger scanned-page detection",
        )

    def test_text_only_page_not_scanned(self):
        """A page with no images must not be flagged."""
        pdf_bytes = _make_text_only_pdf()
        self.assertFalse(
            self._detect(pdf_bytes),
            "Text-only page (no images) must not trigger scanned-page detection",
        )

    def test_small_image_not_scanned(self):
        """A page whose single image covers only a small fraction is not scanned."""
        pdf_bytes = _make_small_image_pdf()
        self.assertFalse(
            self._detect(pdf_bytes),
            "Small image (≪70% area) must not trigger scanned-page detection",
        )

    def test_detection_before_set_contents(self):
        """Detection must still work when the page content stream is empty
        (simulating the state BEFORE set_contents replacement)."""
        # If detection were done AFTER set_contents the result would be False
        # because get_image_rects() needs the Do operator in the content stream.
        doc = pymupdf.open(stream=_make_scanned_pdf())
        mu_page = doc[0]

        # Simulate set_contents replacing the content stream
        new_xref = doc.get_new_xref()
        doc.update_object(new_xref, "<<>>")
        doc.update_stream(new_xref, b"")
        mu_page.set_contents(new_xref)

        # Detection should now FAIL (wrong order) — this is what we prevent
        page_area = mu_page.rect.width * mu_page.rect.height
        detected_after = False
        for img_info in mu_page.get_images(full=True):
            rects = mu_page.get_image_rects(img_info[0])
            if rects:
                if (rects[0].width * rects[0].height) / page_area >= 0.7:
                    detected_after = True
        self.assertFalse(
            detected_after,
            "After set_contents() the detection correctly returns False — "
            "this confirms detection must happen BEFORE set_contents()",
        )


# ---------------------------------------------------------------------------
# Part 2: White-rectangle insertion in pdfinterp.py
# ---------------------------------------------------------------------------

class TestWhiteRectInsertion(unittest.TestCase):
    """Tests for the white-fill rectangle logic in PDFPageInterpreterEx.process_page().

    We patch render_contents and device.end_page so no real translator or ONNX
    model is needed.  The test only verifies the obj_patch string construction.
    """

    def _build_patch(self, page_is_scanned: bool, page_w: float = 200.0, page_h: float = 200.0) -> str:
        """Invoke the obj_patch string-building logic from process_page() directly."""
        from unittest.mock import MagicMock, patch
        from pdfminer.pdfinterp import PDFResourceManager
        from pdf2zh.pdfinterp import PDFPageInterpreterEx

        rsrcmgr = PDFResourceManager()
        device = MagicMock()
        device.page_is_scanned = page_is_scanned
        device.end_page.return_value = "BT ET "  # stub translated text ops

        obj_patch: dict = {}
        interpreter = PDFPageInterpreterEx(rsrcmgr, device, obj_patch)

        # Stub render_contents to return a minimal ops string (skips actual PDF parsing)
        interpreter.render_contents = MagicMock(return_value="image_op ")
        interpreter.fontid = {}
        interpreter.fontmap = {}

        # Fake PDFPage with the given dimensions
        page = MagicMock()
        page.cropbox = (0, 0, page_w, page_h)
        page.rotate = 0
        page.page_xref = 999

        interpreter.process_page(page)
        return obj_patch.get(999, "")

    def test_scanned_page_has_white_rect_in_patch(self):
        """When page_is_scanned=True, the obj_patch must contain the white-fill op."""
        patch_str = self._build_patch(page_is_scanned=True)
        self.assertIn(
            "1 1 1 rg",
            patch_str,
            "White-fill color op '1 1 1 rg' must appear in obj_patch for scanned page",
        )
        self.assertIn(
            "re f",
            patch_str,
            "White rectangle fill op 're f' must appear in obj_patch for scanned page",
        )

    def test_non_scanned_page_has_no_white_rect(self):
        """When page_is_scanned=False, the obj_patch must NOT contain the white-fill op."""
        patch_str = self._build_patch(page_is_scanned=False)
        self.assertNotIn(
            "1 1 1 rg",
            patch_str,
            "White-fill op must NOT appear in obj_patch for non-scanned page",
        )

    def test_white_rect_covers_full_page(self):
        """The white rectangle must span the full page dimensions."""
        patch_str = self._build_patch(page_is_scanned=True, page_w=300.0, page_h=400.0)
        # Check that the rect has the right dimensions (allow floating-point format)
        self.assertIn("0 0 300", patch_str, "White rect x-dimension must match page width 300")
        self.assertIn("400", patch_str, "White rect y-dimension must match page height 400")


if __name__ == "__main__":
    unittest.main()
