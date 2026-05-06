import numpy as np
from typing import List, Tuple


def detect_column_layout(
    text_blocks_x0: List[float],
    page_width: float,
    avg_text_width: float = None,
) -> Tuple[str, float]:
    """
    Detect single or double column layout using x0 coordinate clustering.

    Args:
        text_blocks_x0: List of x0 (left edge) coordinates of text blocks
        page_width: Total page width in points
        avg_text_width: Average text block width (optional, for fallback detection)

    Returns:
        ('single' or 'double', gutter_x0 position if double)
    """
    if len(text_blocks_x0) < 3:
        return 'single', 0.0

    x0 = np.array(text_blocks_x0)
    x0_normalized = x0 / page_width  # normalize to 0-1

    # Simple peak detection: find gaps in x0 distribution
    sorted_x0 = np.sort(x0_normalized)
    gaps = np.diff(sorted_x0)

    if len(gaps) == 0:
        return 'single', 0.0

    # Find large gaps (> 15% of page width)
    # For typical double-column journal: left col ends ~43%, gutter 14-20%, right col starts ~57%
    large_gap_indices = np.where(gaps > 0.15)[0]

    if len(large_gap_indices) >= 1:
        # Likely double column - gap indicates gutter
        gutter_x0 = (sorted_x0[large_gap_indices[0]] + sorted_x0[large_gap_indices[0] + 1]) / 2 * page_width
        return 'double', gutter_x0

    # Fallback: if text blocks are all narrow, check avg_width
    if avg_text_width is not None:
        width_ratio = avg_text_width / page_width
        if width_ratio < 0.50:
            # Narrow blocks but no big gap → might be double col with tight columns
            # Try clustering: split sorted x0 in half, if both halves are tight → double
            mid = len(sorted_x0) // 2
            left_spread = sorted_x0[mid] - sorted_x0[0]
            right_spread = sorted_x0[-1] - sorted_x0[mid]
            if left_spread < 0.45 and right_spread < 0.45:
                gutter_x0 = (sorted_x0[mid] + sorted_x0[mid + 1]) / 2 * page_width
                return 'double', gutter_x0

    return 'single', 0.0


def sort_text_blocks_by_layout(
    text_blocks: List[dict],
    page_width: float,
    page_height: float,
    avg_text_width: float = None,
) -> List[dict]:
    """
    Sort text blocks by reading order, accounting for column layout.

    Each text_block dict must have: x0, y0, x1, y1 (in PDF coordinates, y from bottom)

    Returns sorted list of text_block dicts.
    """
    if not text_blocks:
        return []

    # Detect column layout
    x0_values = [b["x0"] for b in text_blocks]
    layout_type, gutter_x0 = detect_column_layout(x0_values, page_width, avg_text_width)

    if layout_type == 'single':
        # Simple: sort by y0 descending (top to bottom), then x0 ascending
        sorted_blocks = sorted(
            text_blocks,
            key=lambda b: (-b["y0"], b["x0"])
        )
    else:
        # Double column: assign to left or right bucket, then sort within each bucket
        def bucket_key(b):
            if b["x0"] < gutter_x0:
                return (0, -b["y0"], b["x0"])  # left column
            else:
                return (1, -b["y0"], b["x0"])  # right column

        sorted_blocks = sorted(text_blocks, key=bucket_key)

    return sorted_blocks
