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
    m = re.match(r"p\d+_(\w+)_(\d+)\.png", fname)
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
