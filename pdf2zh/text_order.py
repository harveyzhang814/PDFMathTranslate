import numpy as np
from typing import List, Tuple


def detect_column_layout(
    text_blocks_x0: List[float],
    page_width: float,
    avg_text_width: float = None,
    table_boxes: List[dict] = None,
) -> Tuple[str, float]:
    """
    Detect single or double column layout using x0 coordinate clustering.

    Args:
        text_blocks_x0: List of x0 (left edge) coordinates of text blocks
        page_width: Total page width in points
        avg_text_width: Average text block width (optional, for fallback detection)
        table_boxes: List of table bounding boxes from DocLayout [{x0,y0,x1,y1},...] (optional)
                    Used to exclude narrow table cells from gutter calculation

    Returns:
        ('single' or 'double', gutter_x0 position if double)
    """
    if len(text_blocks_x0) < 3:
        return 'single', 0.0

    # Filter out blocks that overlap with table regions (table narrow cells cause false gaps)
    if table_boxes:
        filtered_x0 = []
        for x0 in text_blocks_x0:
            is_table_cell = False
            for tb in table_boxes:
                if abs(x0 - tb["x0"]) < 20:
                    is_table_cell = True
                    break
            if not is_table_cell:
                filtered_x0.append(x0)
        if len(filtered_x0) >= 3:
            text_blocks_x0 = filtered_x0

    x0 = np.array(text_blocks_x0)
    x0_normalized = x0 / page_width

    sorted_x0 = np.sort(x0_normalized)
    gaps = np.diff(sorted_x0)

    if len(gaps) == 0:
        return 'single', 0.0

    large_gap_indices = np.where(gaps > 0.15)[0]

    if len(large_gap_indices) >= 1:
        gutter_x0 = (sorted_x0[large_gap_indices[0]] + sorted_x0[large_gap_indices[0] + 1]) / 2 * page_width
        return 'double', gutter_x0

    if avg_text_width is not None:
        width_ratio = avg_text_width / page_width
        if width_ratio < 0.50:
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
    table_boxes: List[dict] = None,
    caption_boxes: List[dict] = None,
) -> List[dict]:
    """
    Sort text blocks by reading order, accounting for column layout.

    Each text_block dict must have: x0, y0, x1, y1 (in PDF coordinates, y from bottom)

    table_boxes and caption_boxes are from DocLayout and are used to:
    - Group narrow table cells into their parent table region
    - Table captions sort naturally by y0 (captions appear above data in PDF coords)
    """
    if not text_blocks:
        return []

    x0_values = [b["x0"] for b in text_blocks]
    layout_type, gutter_x0 = detect_column_layout(x0_values, page_width, avg_text_width, table_boxes)

    if layout_type == 'single':
        sorted_blocks = sorted(
            text_blocks,
            key=lambda b: (-b["y0"], b["x0"])
        )
    else:
        def bucket_key(b):
            col_bucket = 0 if b["x0"] < gutter_x0 else 1
            return (col_bucket, -b["y0"], b["x0"])

        sorted_blocks = sorted(text_blocks, key=bucket_key)

    return sorted_blocks
