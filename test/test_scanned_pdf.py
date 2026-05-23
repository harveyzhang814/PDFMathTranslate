"""
Tests for pdf2zh/debackground.py

debackground_scanned_pages() is a post-processing step that runs after
translate_stream().  It detects pages with a full-page bitmap background
and inserts a white fill rectangle between the bitmap ops and the
translated text, eliminating the scan-bleed overlap.

All tests here are model-free: they build minimal PDFs directly with
pymupdf and test the module in isolation.
"""

from __future__ import annotations

import io
import re
import struct
import unittest
import zlib

import pymupdf

from pdf2zh.debackground import (
    SCAN_THRESHOLD,
    _insert_white_rect,
    _is_scanned_page,
    debackground_scanned_pages,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_png_white(w: int = 20, h: int = 20) -> bytes:
    """Minimal white PNG."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        c = len(data).to_bytes(4, "big") + tag + data
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return c + crc.to_bytes(4, "big")

    header = chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    raw = b"".join(b"\x00" + b"\xff\xff\xff" * w for _ in range(h))
    idat = chunk(b"IDAT", zlib.compress(raw))
    iend = chunk(b"IEND", b"")
    return b"\x89PNG\r\n\x1a\n" + header + idat + iend


def _make_scanned_pdf(page_w: int = 200, page_h: int = 200) -> bytes:
    """PDF with a full-page image (simulates a scanned document)."""
    doc = pymupdf.open()
    page = doc.new_page(width=page_w, height=page_h)
    page.insert_image(pymupdf.Rect(0, 0, page_w, page_h), stream=_make_png_white())
    page.insert_text((10, 100), "OCR text", fontsize=10)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _make_text_only_pdf(page_w: int = 200, page_h: int = 200) -> bytes:
    """PDF with only text — no background image."""
    doc = pymupdf.open()
    page = doc.new_page(width=page_w, height=page_h)
    page.insert_text((10, 100), "Normal text", fontsize=10)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _make_small_image_pdf(page_w: int = 200, page_h: int = 200) -> bytes:
    """PDF with a small image (5 % of page area) — should not trigger debackground."""
    doc = pymupdf.open()
    page = doc.new_page(width=page_w, height=page_h)
    # 45x45 on 200x200 -> area ratio ~5%
    page.insert_image(pymupdf.Rect(0, 0, 45, 45), stream=_make_png_white())
    page.insert_text((10, 100), "Page with small image", fontsize=10)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _make_synthetic_translated_stream(page_w: float, page_h: float) -> bytes:
    """Build a content stream that mimics the structure produced by
    PDFPageInterpreterEx.process_page():

        q {ops_base} Q 1 0 0 1 {x0} {y0} cm {ops_new}

    ops_base contains the bitmap draw call; ops_new is a minimal BT block.
    """
    ops_base = f"q {page_w} 0 0 {page_h} 0 0 cm /Im0 Do Q "
    ops_new = "BT /tiro 12 Tf 1 0 0 1 50 100 Tm [(Hello)] TJ ET "
    raw = f"q {ops_base}Q 1 0 0 1 0 0 cm {ops_new}"
    return raw.encode()


# ---------------------------------------------------------------------------
# Unit tests: _is_scanned_page
# ---------------------------------------------------------------------------

class TestIsScannedPage(unittest.TestCase):
    """Tests for the per-page detection helper."""

    def test_full_page_image_is_scanned(self):
        doc = pymupdf.open(stream=_make_scanned_pdf())
        self.assertTrue(_is_scanned_page(doc[0]))

    def test_text_only_page_is_not_scanned(self):
        doc = pymupdf.open(stream=_make_text_only_pdf())
        self.assertFalse(_is_scanned_page(doc[0]))

    def test_small_image_is_not_scanned(self):
        doc = pymupdf.open(stream=_make_small_image_pdf())
        self.assertFalse(_is_scanned_page(doc[0]))

    def test_custom_threshold_respected(self):
        """A ~50% image should be detected at threshold=0.4 but not 0.8."""
        doc = pymupdf.open()
        page = doc.new_page(width=200, height=200)
        # 142x142 on 200x200 -> area ratio ~50%
        page.insert_image(pymupdf.Rect(0, 0, 142, 142), stream=_make_png_white())
        self.assertTrue(_is_scanned_page(page, threshold=0.4))
        self.assertFalse(_is_scanned_page(page, threshold=0.8))


# ---------------------------------------------------------------------------
# Unit tests: _insert_white_rect
# ---------------------------------------------------------------------------

class TestInsertWhiteRect(unittest.TestCase):
    """Tests for the content-stream surgery helper."""

    def test_white_rect_inserted_at_boundary(self):
        stream = _make_synthetic_translated_stream(200.0, 300.0)
        result = _insert_white_rect(stream, 200.0, 300.0)
        self.assertIsNotNone(result)
        self.assertIn(b"1 1 1 rg", result)
        self.assertIn(b"re f", result)

    def test_white_rect_wraps_in_q_Q(self):
        """The white rect must be wrapped in q/Q to isolate its colour state."""
        stream = _make_synthetic_translated_stream(200.0, 300.0)
        result = _insert_white_rect(stream, 200.0, 300.0)
        self.assertRegex(
            result.decode(),
            r"q\s+1 1 1 rg\s+[\d. ]+re f Q",
        )

    def test_white_rect_covers_full_page(self):
        """Rectangle dimensions must match the page size passed in."""
        stream = _make_synthetic_translated_stream(594.0, 792.0)
        result = _insert_white_rect(stream, 594.0, 792.0)
        text = result.decode()
        self.assertIn("0 0 594", text)
        self.assertIn("792", text)

    def test_translated_text_follows_white_rect(self):
        """ops_new (BT block) must come AFTER the white rect, not before it."""
        stream = _make_synthetic_translated_stream(200.0, 200.0)
        result = _insert_white_rect(stream, 200.0, 200.0)
        text = result.decode()
        white_pos = text.index("1 1 1 rg")
        bt_pos = text.index("BT /tiro")
        self.assertLess(white_pos, bt_pos,
                        "White rect must appear before the translated BT block")

    def test_returns_none_for_unrecognised_stream(self):
        """Should return None rather than corrupt an unrecognised stream."""
        random_stream = b"BT /Helvetica 12 Tf (Hello) Tj ET"
        self.assertIsNone(_insert_white_rect(random_stream, 200.0, 200.0))

    def test_original_content_preserved(self):
        """Bitmap draw call in ops_base must still be present in the output."""
        stream = _make_synthetic_translated_stream(200.0, 200.0)
        result = _insert_white_rect(stream, 200.0, 200.0)
        self.assertIn(b"/Im0 Do", result)


# ---------------------------------------------------------------------------
# Integration tests: debackground_scanned_pages
# ---------------------------------------------------------------------------

class TestDebackgroundScannedPages(unittest.TestCase):
    """End-to-end tests for the public API."""

    def _make_translated_pdf(self, has_full_page_image: bool) -> bytes:
        """Build a PDF that looks like a translated mono PDF.

        The content stream is crafted to match the structure produced by
        process_page() so _insert_white_rect can find the boundary.

        When has_full_page_image=True we insert a real image via pymupdf
        first, then discover the XObject name pymupdf chose and build the
        synthetic stream with that name so _is_scanned_page can find the
        image rect in the content stream.
        """
        doc = pymupdf.open()
        page = doc.new_page(width=200, height=200)

        if has_full_page_image:
            page.insert_image(pymupdf.Rect(0, 0, 200, 200), stream=_make_png_white())
            # Save + reopen so the image xref is committed and queryable
            buf = io.BytesIO()
            doc.save(buf)
            doc = pymupdf.open(stream=buf.getvalue())
            page = doc[0]

            # Discover the actual XObject name pymupdf assigned
            imgs = page.get_images(full=True)
            # img_info[7] is the name used in the content stream ('Im0', etc.)
            xobj_name = imgs[0][7] if imgs else "Im0"

            # Build synthetic content stream referencing the real XObject name
            ops_base = f"q 200 0 0 200 0 0 cm /{xobj_name} Do Q "
            ops_new = "BT /tiro 12 Tf 1 0 0 1 50 100 Tm [(Hello)] TJ ET "
            synthetic = f"q {ops_base}Q 1 0 0 1 0 0 cm {ops_new}".encode()

            xref = page.get_contents()[0]
            doc.update_stream(xref, synthetic)
        else:
            # Text-only: just a synthetic stream without any image Do.
            # Insert a dummy character so pymupdf creates a content stream
            # (a brand-new blank page has no content stream xref).
            page.insert_text((10, 100), "placeholder", fontsize=10)
            buf = io.BytesIO()
            doc.save(buf)
            doc = pymupdf.open(stream=buf.getvalue())
            page = doc[0]
            ops_new = "BT /tiro 12 Tf 1 0 0 1 50 100 Tm [(Hello)] TJ ET "
            synthetic = f"q Q 1 0 0 1 0 0 cm {ops_new}".encode()
            xref = page.get_contents()[0]
            doc.update_stream(xref, synthetic)

        out = io.BytesIO()
        doc.save(out)
        return out.getvalue()

    def test_scanned_page_gets_white_rect(self):
        pdf = self._make_translated_pdf(has_full_page_image=True)
        result = debackground_scanned_pages(pdf)
        doc = pymupdf.open(stream=result)
        stream = doc.xref_stream(doc[0].get_contents()[0])
        self.assertIn(b"1 1 1 rg", stream,
                      "White fill rect must be present for a scanned page")

    def test_normal_page_unchanged(self):
        """Non-scanned pages must return the same bytes."""
        pdf = self._make_translated_pdf(has_full_page_image=False)
        result = debackground_scanned_pages(pdf)
        self.assertEqual(pdf, result,
                         "Bytes must be unchanged for a page with no full-page image")

    def test_mixed_pdf_only_scanned_pages_modified(self):
        """In a multi-page PDF only the scanned pages should be changed."""
        scanned = self._make_translated_pdf(has_full_page_image=True)
        normal = self._make_translated_pdf(has_full_page_image=False)

        doc_combined = pymupdf.open()
        doc_combined.insert_pdf(pymupdf.open(stream=scanned))
        doc_combined.insert_pdf(pymupdf.open(stream=normal))
        buf = io.BytesIO()
        doc_combined.save(buf)

        result = debackground_scanned_pages(buf.getvalue())
        doc_result = pymupdf.open(stream=result)

        stream_p0 = doc_result.xref_stream(doc_result[0].get_contents()[0])
        stream_p1 = doc_result.xref_stream(doc_result[1].get_contents()[0])

        self.assertIn(b"1 1 1 rg", stream_p0,
                      "Scanned page 0 must have the white rect")
        self.assertNotIn(b"1 1 1 rg", stream_p1,
                         "Normal page 1 must NOT have the white rect")

    def test_threshold_parameter(self):
        """threshold=2.0 (impossible ratio) should leave the PDF unchanged."""
        pdf = self._make_translated_pdf(has_full_page_image=True)
        result = debackground_scanned_pages(pdf, threshold=2.0)
        self.assertEqual(pdf, result)


if __name__ == "__main__":
    unittest.main()
