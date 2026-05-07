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

# ── Formatting constants ────────────────────────────────────────────────────
_FONT_BODY = "宋体"
_FONT_HEADING = "黑体"
_FONT_CAPTION = "仿宋"
_SIZE_BODY = 12        # pt
_SIZE_HEADING = 14     # pt
_SIZE_CAPTION = 10     # pt
# 240 = single, 360 = 1.5×, 480 = double (Word line units: twips/240)
_LINE_SPACING = 360

# XML 1.0 only allows: #x9 | #xA | #xD | [#x20-#xD7FF] | [#xE000-#xFFFD] | [#x10000-#x10FFFF]
_XML_INVALID = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff￾￿]")

# CJK languages whose translated blocks must contain at least one CJK character
_CJK_LANGS = {"zh", "zh-cn", "zh-tw", "zh-hans", "zh-hant", "ja", "ko"}

# Unicode ranges covering CJK Unified Ideographs and common CJK extensions
_HAS_CJK = re.compile(r"[⺀-鿿豈-﫿︰-﹏]")


def _set_cjk_font(run, font_name: str) -> None:
    """Set both the Latin and CJK (eastAsia) font on a run via OOXML."""
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.insert(0, rFonts)
    rFonts.set(qn("w:eastAsia"), font_name)
    rFonts.set(qn("w:hAnsi"), font_name)


def _set_para_line_spacing(para) -> None:
    """Apply 1.5× line spacing to a paragraph via OOXML."""
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    pPr = para._p.get_or_add_pPr()
    for child in list(pPr):
        if child.tag == qn("w:spacing"):
            pPr.remove(child)
    spacing = OxmlElement("w:spacing")
    spacing.set(qn("w:line"), str(_LINE_SPACING))
    spacing.set(qn("w:lineRule"), "auto")
    pPr.append(spacing)


def _add_body_para(doc, text: str):
    """Add a left-aligned body paragraph in 宋体 12pt with 1.5× line spacing."""
    from docx.shared import Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    _set_para_line_spacing(p)
    run = p.add_run(text)
    run.font.name = _FONT_BODY
    run.font.size = Pt(_SIZE_BODY)
    _set_cjk_font(run, _FONT_BODY)
    return p


def _add_caption_para(doc, text: str):
    """Add a centred italic caption paragraph in 仿宋 10pt grey."""
    from docx.shared import Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(text)
    run.font.name = _FONT_CAPTION
    run.font.size = Pt(_SIZE_CAPTION)
    run.italic = True
    run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
    _set_cjk_font(run, _FONT_CAPTION)
    return p


def _style_heading(heading) -> None:
    """Apply 黑体 14pt bold styling to a heading paragraph's runs."""
    from docx.shared import Pt
    for run in heading.runs:
        run.font.name = _FONT_HEADING
        run.font.size = Pt(_SIZE_HEADING)
        run.bold = True
        _set_cjk_font(run, _FONT_HEADING)


def _sanitize(text: str) -> str:
    """Strip characters that are illegal in XML 1.0 (used by .docx)."""
    return _XML_INVALID.sub("", text)


def _join_pdf_lines(text: str) -> str:
    """Collapse PDF visual line-breaks into spaces within a single paragraph.

    Three cases:
      • hyphenated break  "word-\\nrest"  → "wordrest"
      • mid-word break    "AT\\nR"        → "ATR"   (e.g. column-split acronyms)
      • normal break      "foo\\nbar"     → "foo bar"
    """
    text = re.sub(r"-\n", "", text)                          # de-hyphenate
    text = re.sub(r"(?<=[^\s])\n(?=[^\s])", "", text)        # mid-word
    text = text.replace("\n", " ")
    return re.sub(r" {2,}", " ", text).strip()


# Sentence-ending punctuation that signals a paragraph boundary when followed by \n
_PARA_SPLIT_RE = re.compile(
    r"(?<=[。！？!?])\n"          # CJK / ASCII sentence end + newline
    r"|(?<=\.)\n(?=[A-Z一-鿿])"  # period + newline before capital/CJK
    r"|\n{2,}"                    # explicit blank line
)


def _split_paragraphs(text: str) -> list[str]:
    """Split a pymupdf block into individual paragraphs.

    A single block sometimes contains multiple paragraphs separated by a blank
    line or a sentence-ending newline.  Split on those boundaries first so that
    each paragraph is joined independently.
    """
    parts = _PARA_SPLIT_RE.split(text)
    return [p for p in parts if p.strip()]


def _should_include(text: str, lang_out: str) -> bool:
    """Return False for untranslated blocks when output language is CJK.

    Tables and abandon regions are masked during translation and keep their
    original language.  Filter them out so only translated text appears in the
    Word document.
    """
    if lang_out.lower() not in _CJK_LANGS:
        return True
    return bool(_HAS_CJK.search(text))


# Caption detection: text must START with one of these patterns.
# Using start-anchor regexes prevents false positives like "超声心动图" matching "图".
_CAPTION_RE = re.compile(
    r'^(?:'
    r'fig\.?\s*\d'           # Fig 1 / Fig. 1
    r'|figure\s*\d'          # Figure 1
    r'|table\s*\d'           # Table 1
    r'|panel\s*[a-z\d]'      # Panel A / Panel 1
    r'|[图表]\s*\d'           # 图1 / 表1
    r')',
    re.IGNORECASE,
)


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
    """Add a centred image and an optional caption paragraph."""
    from docx.shared import Inches
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
        _add_caption_para(doc, caption)


def export_pdf_to_word(
    pdf_mono_path: str,
    elem_dir: Optional[str],
    output_docx_path: str,
    lang_out: str = "zh",
    pages: Optional[List[int]] = None,
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
    except ImportError:
        raise RuntimeError("python-docx not installed. Run: pip install python-docx")

    doc = Document()
    doc_mono = pymupdf.open(pdf_mono_path)

    # Element images: elem_dir/elements/p{N}_{type}_{idx}.png
    elements_subdir = (
        os.path.join(elem_dir, "elements") if elem_dir else ""
    )

    # Load figure layout for proximity-based caption↔image matching
    figure_layout = _load_figure_layout(elements_subdir) if elements_subdir else {}

    for pageno, page in enumerate(doc_mono):
        if pages is not None and pageno not in pages:
            continue
        # Page heading
        _style_heading(doc.add_heading(f"Page {pageno + 1}", level=2))

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

        # Per-page figure layout and usage tracking for proximity matching
        page_figures = figure_layout.get(pageno, [])
        used_figures: set = set()
        next_elem_idx: dict = {"figure": 1, "table": 1}  # fallback sequential counter

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
        # sort_text_blocks_by_layout expects y-from-bottom (PDF coords).
        # pymupdf uses y-from-top, so flip before sorting and restore after.
        ph = page.rect.height
        flipped = [{**b, "y0": ph - b["y1"], "y1": ph - b["y0"]} for b in blocks]
        sorted_flipped = sort_text_blocks_by_layout(flipped, page.rect.width, ph, avg_w)
        blocks = [{**b, "y0": ph - b["y1"], "y1": ph - b["y0"]} for b in sorted_flipped]

        for block in blocks:
            raw = _sanitize(block["content"])
            # Split block into paragraphs first so two paragraphs packed into
            # one pymupdf block don't get merged into one Word paragraph.
            para_texts = [_join_pdf_lines(p) for p in _split_paragraphs(raw)]

            for text in para_texts:
                if not text or not _should_include(text, lang_out):
                    continue

                # Caption blocks start with "Fig N", "Table N", "图N", "表N", etc.
                # Require a leading pattern so body text containing "图" is not misidentified.
                is_caption = len(text) < 300 and bool(_CAPTION_RE.match(text))

                if is_caption:
                    # Find the spatially nearest figure image for this caption
                    matched = _find_nearest_figure(block, page_figures, used_figures)
                    if matched:
                        # Image first, caption below (standard academic convention)
                        fig_i, image_file = matched
                        used_figures.add(fig_i)
                        parsed = _parse_elem_filename(image_file)
                        if parsed:
                            elem_by_idx.pop((parsed["type"], parsed["idx"]), None)
                        img_path = os.path.join(elements_subdir, image_file)
                        if os.path.exists(img_path):
                            _add_image_to_doc(doc, img_path, "")
                        _add_caption_para(doc, text)
                    else:
                        # Fallback: caption first for tables (standard table convention)
                        _add_caption_para(doc, text)
                        for elem_type in ["figure", "table"]:
                            k = (elem_type, next_elem_idx[elem_type])
                            if k in elem_by_idx:
                                ef = elem_by_idx.pop(k)
                                next_elem_idx[elem_type] += 1
                                img_path = os.path.join(elements_subdir, ef)
                                _add_image_to_doc(doc, img_path, _make_caption_label(ef))
                                break
                else:
                    _add_body_para(doc, text)

        # After all text blocks, dump any remaining images (no caption found)
        for (elem_type, idx), ef in sorted(elem_by_idx.items()):
            img_path = os.path.join(elements_subdir, ef)
            label = _make_caption_label(ef)
            _add_image_to_doc(doc, img_path, label)

    doc_mono.close()
    doc.save(output_docx_path)
    logger.info(f"Saved Word doc: {output_docx_path}")
    return output_docx_path


def _load_figure_layout(elements_subdir: str) -> dict:
    """Load figures.json and return {pageno: [figure_info, ...]}."""
    import json
    figures_json = os.path.join(elements_subdir, "figures.json")
    if not os.path.exists(figures_json):
        return {}
    with open(figures_json, encoding="utf-8") as f:
        figures = json.load(f)
    layout: dict = {}
    for fig in figures:
        layout.setdefault(fig["pageno"], []).append(fig)
    return layout


def _find_nearest_figure(
    caption: dict,
    page_figures: List[dict],
    used: set,
) -> Optional[tuple]:
    """Return (list_index, image_file) of the nearest unused figure, or None."""
    best_i = None
    best_score = float("inf")
    cap_cx = (caption["x0"] + caption["x1"]) / 2

    for i, fig in enumerate(page_figures):
        if i in used:
            continue
        if caption["y0"] >= fig["y1"]:
            y_gap = caption["y0"] - fig["y1"]
        elif caption["y1"] <= fig["y0"]:
            y_gap = fig["y0"] - caption["y1"]
        else:
            y_gap = 0
        fig_cx = (fig["x0"] + fig["x1"]) / 2
        score = y_gap + abs(cap_cx - fig_cx) * 0.3
        if score < best_score:
            best_score = score
            best_i = i

    if best_i is not None and best_score < 300:
        return best_i, page_figures[best_i]["image_file"]
    return None


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
