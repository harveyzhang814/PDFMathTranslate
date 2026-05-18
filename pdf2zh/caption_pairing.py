from typing import List


def pair_figure_caption(
    figure_boxes: List[dict],
    caption_boxes: List[dict],
) -> List[dict]:
    """
    Pair each figure with its nearest caption using spatial proximity.

    Coordinates are in screen space (pixels, y from top).

    Args:
        figure_boxes: [{x0, y0, x1, y1, idx, pageno}, ...]
        caption_boxes: [{x0, y0, x1, y1, text, pageno}, ...]

    Returns:
        [{idx, page, image_ref, caption, fig_bbox}, ...]
    """
    used = set()
    paired = []

    for fig in figure_boxes:
        best_i = None
        best_score = float("inf")

        for i, cap in enumerate(caption_boxes):
            if i in used or cap["pageno"] != fig["pageno"]:
                continue

            # Vertical gap between figure and caption edges
            if cap["y0"] >= fig["y1"]:          # caption below figure
                y_gap = cap["y0"] - fig["y1"]
            elif cap["y1"] <= fig["y0"]:         # caption above figure
                y_gap = fig["y0"] - cap["y1"]
            else:
                y_gap = 0                        # overlapping

            # Horizontal centre distance (penalised less than vertical)
            fig_cx = (fig["x0"] + fig["x1"]) / 2
            cap_cx = (cap["x0"] + cap["x1"]) / 2
            x_dist = abs(fig_cx - cap_cx)

            score = y_gap + x_dist * 0.3
            if score < best_score:
                best_score = score
                best_i = i

        # Accept only captions within 120 px of the figure
        cap_text = ""
        if best_i is not None and best_score < 120:
            cap_text = caption_boxes[best_i].get("text", "")
            used.add(best_i)

        image_ref = f"p{fig['pageno'] + 1}_figure_{fig['idx']:03d}.png"
        paired.append({
            "idx": fig["idx"],
            "page": fig["pageno"] + 1,
            "image_ref": image_ref,
            "caption": cap_text,
            "fig_bbox": {
                "x0": fig["x0"], "y0": fig["y0"],
                "x1": fig["x1"], "y1": fig["y1"],
            },
        })

    return paired


def build_element_manifest(
    figure_pairings: List[dict],
    output_dir: str,
) -> str:
    """
    Write elements/manifest.json alongside the extracted images.
    """
    import json
    import os

    manifest_path = os.path.join(output_dir, "elements", "manifest.json")
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)

    manifest = {
        "elements": figure_pairings,
        "total_figures": len(figure_pairings),
    }

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    return manifest_path
