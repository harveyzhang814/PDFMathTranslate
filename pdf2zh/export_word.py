"""
Export translated PDF content as a Word document.

Pipeline:
1. translate() → mono.pdf + cropped figures/tables
2. pymupdf extracts text blocks with positions
3. Sort by reading order (column-aware geometric sort)
4. python-docx assembles document with text + images interleaved with captions
"""
import logging
import os
import re
from typing import List, Optional

import numpy as np
import pymupdf

from .text_order import sort_text_blocks_by_layout

logger = logging.getLogger(__name__)

# Keywords that identify a caption block
CAPTION_KEYWORDS = [
    "fig", "figure", "table", "panel",
    "表", "图", "fig.", "panel a", "panel b",
]


def _extract_page_text_blocks(page: pymupdf.Page) -> List[dict]:
    """Extract text blocks with positions from a pymupdf page."""
    blocks = page.get_text("blocks")
    return [
        {"x0": b[0], "y0": b[1], "x1": b[2], "y1": b[3], "content": b[4].strip()}
        for b in blocks if b[4].strip()
    ]


def _parse_elem_filename(fname: str) -> Optional[dict]:
    """Parse element filename like 'p2_table_001.png' → {type: 'table', idx: 1}."""
    m = re.match(r"p\d+_(\w+)_(\d+)\.png", fname)
    if not m:
        return None
    return {"type": m.group(1), "idx": int(m.group(2))}


def _add_image_to_doc(doc, img_path: str, caption: str) -> None:
    """Add an image and its caption to the document."""
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    try:
        run = p.add_run()
        run.add_picture(img_path, width=Inches(5.5))
    except Exception as e:
        logger.warning(f"Failed to embed image {img_path}: {e}")
        return

    if caption:
        cap_p = doc.add_paragraph()
        cap_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cap_run = cap_p.add_run(caption)
        cap_run.italic = True
        cap_run.font.size = Pt(9)
        cap_run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)


def export_pdf_to_word(
    pdf_mono_path: str,
    elem_dir: Optional[str],
    output_docx_path: str,
    lang_out: str = "zh",
) -> str:
    """
    Convert translated mono PDF + extracted elements → .docx file.

    Args:
        pdf_mono_path: path to translated mono.pdf
        elem_dir: root directory containing "elements/" subdir with cropped images
        output_docx_path: output .docx path
        lang_out: output language

    Returns:
        Path to the generated .docx file
    """
    try:
        from docx import Document
        from docx.shared import Pt, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
    except ImportError:
        raise RuntimeError("python-docx not installed. Run: pip install python-docx")

    doc = Document()
    doc_mono = pymupdf.open(pdf_mono_path)

    # Element images: elem_dir/elements/p{N}_{type}_{idx}.png
    elements_subdir = (
        os.path.join(elem_dir, "elements") if elem_dir else ""
    )

    for pageno, page in enumerate(doc_mono):
        # Page heading
        doc.add_heading(f"Page {pageno + 1}", level=2)

        # Load image files for this page
        elem_files: List[str] = []
        elem_by_idx: dict = {}  # {(type, idx): filename}
        if elements_subdir and os.path.isdir(elements_subdir):
            elem_prefix = f"p{pageno + 1}_"
            elem_files = sorted(
                f for f in os.listdir(elements_subdir)
                if f.startswith(elem_prefix) and f.endswith(".png")
            )
            for ef in elem_files:
                parsed = _parse_elem_filename(ef)
                if parsed:
                    elem_by_idx[(parsed["type"], parsed["idx"])] = ef

        # Track which element indices have been consumed
        next_elem_idx: dict = {"figure": 1, "table": 1}

        # Extract and sort text blocks
        blocks = _extract_page_text_blocks(page)
        if not blocks:
            # No text, just add any leftover images
            for ef in elem_files:
                img_path = os.path.join(elements_subdir, ef)
                label = _make_caption_label(ef)
                _add_image_to_doc(doc, img_path, label)
            continue

        avg_w = np.mean([max(b["x1"] - b["x0"], 1) for b in blocks])
        blocks = sort_text_blocks_by_layout(blocks, page.rect.width, page.rect.height, avg_w)

        for block in blocks:
            text = block["content"]
            if not text:
                continue

            # Check if this block is a caption
            is_caption = (
                len(text) < 300
                and not text.endswith(".")
                and any(kw in text.lower() for kw in CAPTION_KEYWORDS)
            )

            if is_caption:
                # Add caption text first
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run = p.add_run(text)
                run.italic = True
                run.font.size = Pt(9)
                run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

                # Try to insert the corresponding image immediately after
                for elem_type in ["figure", "table"]:
                    k = (elem_type, next_elem_idx[elem_type])
                    if k in elem_by_idx:
                        ef = elem_by_idx.pop(k)
                        next_elem_idx[elem_type] += 1
                        img_path = os.path.join(elements_subdir, ef)
                        label = _make_caption_label(ef)
                        _add_image_to_doc(doc, img_path, label)
                        break
            else:
                # Regular paragraph
                p = doc.add_paragraph(text)
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT

        # After all text blocks, dump any remaining images (no caption found)
        for (elem_type, idx), ef in sorted(elem_by_idx.items()):
            img_path = os.path.join(elements_subdir, ef)
            label = _make_caption_label(ef)
            _add_image_to_doc(doc, img_path, label)

    doc_mono.close()
    doc.save(output_docx_path)
    logger.info(f"Saved Word doc: {output_docx_path}")
    return output_docx_path


def _make_caption_label(fname: str) -> str:
    """Convert 'p2_table_001.png' → 'Table 1'."""
    parsed = _parse_elem_filename(fname)
    if not parsed:
        return fname.replace("_", " ").replace(".png", "")
    type_label = (
        "Table" if parsed["type"] == "table"
        else "Figure" if parsed["type"] == "figure"
        else parsed["type"].capitalize()
    )
    return f"{type_label} {parsed['idx']}"
