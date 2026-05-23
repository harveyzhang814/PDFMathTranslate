"""
Post-processing step: remove scan background bleed from translated PDFs.

Some PDFs are scanned documents: each page contains a full-page bitmap image
(the actual visible text rendered as pixels) and an invisible OCR text layer on
top.  After translation the OCR layer is replaced by the target language, but
the bitmap remains — causing the original scan to show through the translated
text.

This module runs as a post-processing step AFTER translate_stream() has
produced the mono PDF.  It is completely independent of the core translation
pipeline; the pipeline code is unchanged.

Approach
--------
For each page in the translated mono PDF:
1. Detect whether a full-page bitmap image covers ≥ THRESHOLD of the page area
   (same criterion used to identify scanned backgrounds).
2. If so, locate the boundary between ops_base (which contains the bitmap Do
   operator) and ops_new (the translated text) in the page content stream.
   This boundary is the string ``Q 1 0 0 1 {x0} {y0} cm`` that
   process_page() always emits.
3. Insert ``q 1 1 1 rg 0 0 {w} {h} re f Q`` at that point — a white-fill
   rectangle wrapped in its own q/Q graphics-state scope so it does not
   affect the text colour that follows.

Only pages that are positively identified as scanned are modified; all other
pages are left byte-for-byte identical.
"""

from __future__ import annotations

import io
import re
import logging
from typing import Optional

import pymupdf

log = logging.getLogger(__name__)

# Fraction of page area that an image must cover to be treated as a
# full-page scan background.
SCAN_THRESHOLD: float = 0.70


def _is_scanned_page(page: pymupdf.Page, threshold: float = SCAN_THRESHOLD) -> bool:
    """Return True if *page* has a bitmap image covering ≥ threshold of its area."""
    page_area = page.rect.width * page.rect.height
    if page_area <= 0:
        return False
    for img_info in page.get_images(full=True):
        rects = page.get_image_rects(img_info[0])
        if rects:
            img_area = rects[0].width * rects[0].height
            if img_area / page_area >= threshold:
                return True
    return False


def _insert_white_rect(stream: bytes, page_w: float, page_h: float) -> Optional[bytes]:
    """Insert a white-fill rectangle between ops_base and ops_new.

    The translated page content stream has the structure produced by
    ``PDFPageInterpreterEx.process_page()``::

        q {ops_base} Q 1 0 0 1 {x0} {y0} cm {ops_new}

    The insertion point is immediately after the outer ``Q`` that closes
    ops_base, which is always followed by ``1 0 0 1`` (the start of the
    coordinate-transform for ops_new).

    Returns the modified stream bytes, or None if the expected pattern is
    not found (meaning the stream was not produced by our pipeline).
    """
    # The boundary pattern: "Q " followed by the affine-transform prefix.
    # We use a regex so whitespace variations (spaces vs newlines) are handled.
    # Group 1 captures everything up to and including the outer Q.
    # Group 2 captures the rest (coordinate transform + ops_new).
    pattern = re.compile(
        rb"(.*\bQ\s+)"          # everything up to the outer closing Q
        rb"(1 0 0 1 [\d. -]+cm\s+BT\s)",  # coordinate transform + start of ops_new
        re.DOTALL,
    )
    m = pattern.search(stream)
    if m is None:
        return None

    white_rect = (
        f"q 1 1 1 rg 0 0 {page_w:f} {page_h:f} re f Q "
    ).encode()

    return m.group(1) + white_rect + stream[m.start(2):]


def debackground_scanned_pages(
    pdf_bytes: bytes,
    threshold: float = SCAN_THRESHOLD,
) -> bytes:
    """Blank scan backgrounds in a translated mono PDF.

    Examines every page of *pdf_bytes*.  Pages whose background is a
    full-page bitmap (area ≥ *threshold* × page area) receive a white fill
    rectangle inserted between the bitmap drawing ops and the translated
    text.  Pages that do not match are left untouched.

    Parameters
    ----------
    pdf_bytes:
        Raw bytes of the translated mono PDF (output of translate_stream).
    threshold:
        Minimum ratio of image area to page area for a page to be treated
        as a scanned background.  Default: 0.70 (70 %).

    Returns
    -------
    bytes
        Modified PDF bytes.  If no pages required modification the input
        bytes are returned unchanged.
    """
    doc = pymupdf.open(stream=pdf_bytes)
    modified_count = 0

    for page in doc:
        if not _is_scanned_page(page, threshold):
            continue

        xrefs = page.get_contents()
        if not xrefs:
            continue

        stream = doc.xref_stream(xrefs[0])
        page_w = page.rect.width
        page_h = page.rect.height

        new_stream = _insert_white_rect(stream, page_w, page_h)
        if new_stream is None:
            log.debug(
                "debackground: page %d looks scanned but boundary pattern "
                "not found — skipping",
                page.number,
            )
            continue

        doc.update_stream(xrefs[0], new_stream)
        modified_count += 1
        log.debug("debackground: blanked scan background on page %d", page.number)

    if modified_count == 0:
        return pdf_bytes

    log.info("debackground: blanked %d scanned page(s)", modified_count)
    buf = io.BytesIO()
    doc.save(buf, deflate=True, garbage=3)
    return buf.getvalue()
