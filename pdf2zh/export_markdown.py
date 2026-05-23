"""
Export translated PDF content as Markdown with Obsidian-style image links.

Pipeline:
1. translate() → mono.pdf + cropped figures/tables in elem_dir/elements/
2. Copy element images to output_dir/images/
3. pymupdf extracts text blocks with positions
4. Sort by reading order (column-aware geometric sort)
5. Assemble Markdown: paragraphs, image wikilinks, italic captions, --- page separators
"""
import logging
import os
import re
import shutil
from pathlib import Path
from typing import List, Optional

import numpy as np
import pymupdf

from .text_order import sort_text_blocks_by_layout

logger = logging.getLogger(__name__)

CAPTION_KEYWORDS = [
    "fig", "figure", "table", "panel",
    "表", "图", "fig.", "panel a", "panel b",
]

# Characters that unambiguously end a sentence or a self-contained token.
# A block whose last non-space character is NOT in this set may be a soft-
# wrapped line and should be joined to the next block.
_SENTENCE_ENDS = frozenset(".!?。！？…」』\"'")


def _merge_broken_lines(blocks: List[dict]) -> List[dict]:
    """Join adjacent blocks that were split by PDF soft line-wrapping.

    In two-column PDFs each visual line is often a separate text block.
    When the last character of block N is NOT a sentence-ending punctuation
    mark AND the first character of block N+1 is a lowercase ASCII letter
    (continuation of an English word split at the column edge), the two
    blocks are merged: their texts are concatenated directly (no space
    needed because the split happens mid-word).

    CJK text is not merged this way because Chinese sentences have no
    inter-word spaces and break cleanly at character boundaries.
    """
    if not blocks:
        return blocks

    merged: List[dict] = []
    carry = dict(blocks[0])  # working copy of the accumulator block

    for nxt in blocks[1:]:
        last_ch = carry["content"].rstrip()[-1] if carry["content"].rstrip() else ""
        first_ch = nxt["content"].lstrip()[:1] if nxt["content"].lstrip() else ""

        if last_ch and last_ch not in _SENTENCE_ENDS and first_ch.islower():
            # Soft-wrapped English word: glue directly, extend bounding box
            carry["content"] = carry["content"].rstrip() + nxt["content"].lstrip()
            carry["x1"] = max(carry["x1"], nxt["x1"])
            carry["y1"] = max(carry["y1"], nxt["y1"])
        else:
            merged.append(carry)
            carry = dict(nxt)

    merged.append(carry)
    return merged


def _parse_elem_filename(fname: str) -> Optional[dict]:
    """Parse element filename like 'p2_table_001.png' → {type: 'table', idx: 1}."""
    m = re.match(r"p\d+_([a-z]+)_(\d+)\.png", fname)
    if not m:
        return None
    return {"type": m.group(1), "idx": int(m.group(2))}


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


def _is_caption(text: str) -> bool:
    """Return True when text looks like a figure/table caption."""
    return (
        len(text) < 300
        and not text.endswith(".")
        and any(kw in text.lower() for kw in CAPTION_KEYWORDS)
    )


def _is_header_footer(block: dict, page_height: float, margin: float = 0.08) -> bool:
    """Return True when a block sits inside the top or bottom margin of a page.

    pymupdf uses y-from-top coordinates, so:
    - header zone: y1 < page_height * margin   (block is entirely near the top)
    - footer zone: y0 > page_height * (1 - margin)

    The default margin of 8 % matches the typical header/footer band in
    academic journal PDFs (running titles, page numbers, journal URLs).
    """
    top_edge = page_height * margin
    bottom_edge = page_height * (1.0 - margin)
    return block["y1"] < top_edge or block["y0"] > bottom_edge


def _is_vertical_text_block(text: str) -> bool:
    """Return True when a block's content looks like rotated/vertical text.

    When a PDF stores 90°-rotated text (journal watermarks, sidebar DOI
    strings, etc.), pymupdf's text extractor emits each character on its
    own line inside a single block.  The tell-tale sign is that virtually
    every non-empty line is 1–2 characters long.

    Threshold: ≥ 5 non-empty lines AND average line length ≤ 2.0.
    """
    non_empty = [l for l in text.split("\n") if l.strip()]
    if len(non_empty) < 5:
        return False
    avg_len = sum(len(l) for l in non_empty) / len(non_empty)
    return avg_len <= 2.0


def _extract_page_text_blocks(page: pymupdf.Page) -> List[dict]:
    """Extract text blocks with positions from a pymupdf page.

    Filters applied:
    1. Empty / single-character blocks are discarded.
    2. Vertical-text blocks (avg line length ≤ 2, ≥ 5 lines) are discarded:
       they arise from rotated/vertical text such as journal watermarks and
       DOI sidebars where every glyph is on its own line within the block.
    3. Header/footer blocks (top or bottom 8 % of page height) are discarded.
    """
    ph = page.rect.height
    blocks = page.get_text("blocks")
    candidates = [
        {"x0": b[0], "y0": b[1], "x1": b[2], "y1": b[3], "content": b[4].strip()}
        for b in blocks
        if len(b[4].strip()) > 1 and not _is_vertical_text_block(b[4])
    ]
    return [b for b in candidates if not _is_header_footer(b, ph)]


def export_pdf_to_markdown(
    pdf_mono_path: str,
    elem_dir: Optional[str],
    output_dir: str,
    lang_out: str = "zh",
) -> str:
    """
    Convert translated mono PDF + extracted elements → Markdown file.

    Args:
        pdf_mono_path: path to translated mono.pdf
        elem_dir: root directory containing "elements/" subdir with cropped images
        output_dir: per-task folder; will contain <stem>.md and images/
        lang_out: output language (reserved for future CJK filtering)

    Returns:
        Path to the generated .md file
    """
    stem = Path(pdf_mono_path).stem
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    images_dir = output_path / "images"
    images_dir.mkdir(exist_ok=True)

    # Copy all element PNGs into images/ before opening the PDF
    elements_subdir = os.path.join(elem_dir, "elements") if elem_dir else None
    if elements_subdir and os.path.isdir(elements_subdir):
        for fname in os.listdir(elements_subdir):
            if fname.endswith(".png"):
                shutil.copy(
                    os.path.join(elements_subdir, fname),
                    str(images_dir / fname),
                )

    lines: List[str] = []

    with pymupdf.open(pdf_mono_path) as doc_mono:
        for pageno, page in enumerate(doc_mono):
            if pageno > 0:
                lines.extend(["", "---", ""])

            # Collect element files for this page
            elem_by_idx: dict = {}
            elem_files: List[str] = []
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

            next_elem_idx: dict = {"figure": 1, "table": 1}

            blocks = _extract_page_text_blocks(page)
            if not blocks:
                # No text: dump all images for this page
                for ef in elem_files:
                    lines.append(f"![[images/{ef}]]")
                    lines.append("")
                continue

            # Sort blocks in reading order.
            # sort_text_blocks_by_layout expects y-from-bottom (PDF coords);
            # pymupdf uses y-from-top, so flip before sorting and restore after.
            avg_w = np.mean([max(b["x1"] - b["x0"], 1) for b in blocks])
            ph = page.rect.height
            flipped = [{**b, "y0": ph - b["y1"], "y1": ph - b["y0"]} for b in blocks]
            sorted_blocks = sort_text_blocks_by_layout(flipped, page.rect.width, ph, avg_w)
            sorted_blocks = _merge_broken_lines(sorted_blocks)

            for block in sorted_blocks:
                text = block["content"]
                if not text:
                    continue

                if _is_caption(text):
                    # Insert the next available image before the caption
                    for elem_type in ["figure", "table"]:
                        k = (elem_type, next_elem_idx[elem_type])
                        if k in elem_by_idx:
                            ef = elem_by_idx.pop(k)
                            next_elem_idx[elem_type] += 1
                            lines.append(f"![[images/{ef}]]")
                            lines.append("")
                            break
                    lines.append(f"*{text}*")
                    lines.append("")
                else:
                    lines.append(text)
                    lines.append("")

            # Any images not consumed by caption matching go at the end of the page
            for key, ef in sorted(elem_by_idx.items()):
                lines.append(f"![[images/{ef}]]")
                lines.append("")

    # Strip trailing blank lines
    while lines and lines[-1] == "":
        lines.pop()

    md_path = str(output_path / f"{stem}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    logger.info(f"Saved Markdown: {md_path}")
    return md_path
