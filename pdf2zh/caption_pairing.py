from typing import List, Tuple


def pair_figure_caption(
    figure_boxes: List[dict],
    caption_data: dict,
) -> List[dict]:
    """
    Pair each figure with its caption text based on vertical proximity.

    In PDF coordinates (y from bottom), a figure's caption appears BELOW the figure
    (caption y0 < figure y0, since higher y0 = higher/earlier on page).

    Args:
        figure_boxes: List of detected figure boxes, each with {x0, y0, x1, y1, idx}
        caption_data: Dict {(pageno, "figure", idx): caption_text}

    Returns:
        List of dicts: [{"idx": 1, "image_ref": "p3_figure_001.png", "caption": "FIG. 2..."}, ...]
    """
    paired = []

    for fig in figure_boxes:
        idx = fig["idx"]
        cap_text = caption_data.get((fig["pageno"], "figure", idx), "")

        # Build image ref from page number and figure idx
        image_ref = f"p{fig['pageno']+1}_figure_{idx:03d}.png"

        paired.append({
            "idx": idx,
            "page": fig["pageno"] + 1,
            "image_ref": image_ref,
            "caption": cap_text,
            "fig_bbox": {"x0": fig["x0"], "y0": fig["y0"], "x1": fig["x1"], "y1": fig["y1"]},
        })

    return paired


def build_element_manifest(
    figure_pairings: List[dict],
    output_dir: str,
) -> str:
    """
    Build a JSON manifest of all extracted elements with their metadata.
    Saved as elements/manifest.json alongside the extracted images.
    """
    import json, os

    manifest_path = os.path.join(output_dir, "elements", "manifest.json")
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)

    manifest = {
        "elements": figure_pairings,
        "total_figures": len(figure_pairings),
    }

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    return manifest_path
