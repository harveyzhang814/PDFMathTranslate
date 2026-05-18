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


def _extract_page_text_blocks(page: pymupdf.Page) -> List[dict]:
    """Extract text blocks with positions from a pymupdf page."""
    blocks = page.get_text("blocks")
    return [
        {"x0": b[0], "y0": b[1], "x1": b[2], "y1": b[3], "content": b[4].strip()}
        for b in blocks if b[4].strip()
    ]


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
    elements_subdir = os.path.join(elem_dir, "elements") if elem_dir else ""
    if elements_subdir and os.path.isdir(elements_subdir):
        for fname in os.listdir(elements_subdir):
            if fname.endswith(".png"):
                shutil.copy(
                    os.path.join(elements_subdir, fname),
                    str(images_dir / fname),
                )

    doc_mono = pymupdf.open(pdf_mono_path)
    lines: List[str] = []

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
        sorted_flipped = sort_text_blocks_by_layout(flipped, page.rect.width, ph, avg_w)
        sorted_blocks = [{**b, "y0": ph - b["y1"], "y1": ph - b["y0"]} for b in sorted_flipped]

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

    doc_mono.close()

    # Strip trailing blank lines
    while lines and lines[-1] == "":
        lines.pop()

    md_path = str(output_path / f"{stem}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    logger.info(f"Saved Markdown: {md_path}")
    return md_path
