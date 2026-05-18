"""
Unit tests for figure/table crop coordinate logic in high_level.py.

The DocLayout model and the numpy page image both use y=0 at the top of the
image (standard screen/pixel convention).  Slicing the numpy array therefore
requires the *raw* xyxy coordinates — no y-flip.  These tests verify that the
correct formula captures the target region and that the old (broken) flipped
formula does not.
"""
import os
import tempfile
import unittest

import numpy as np


def _make_page_image(height=400, width=300):
    """Return a BGR numpy array with a red rectangle at a known location.

    Red square occupies rows 20-79, cols 80-179 (y from top, 0-indexed).
    With a 400px-tall image the y-flipped region (rows ~321-380) is clearly
    in the bottom half and contains no red pixels.
    """
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[20:80, 80:180] = [0, 0, 255]  # BGR red
    return img


def _crop(img, x0, y0, x1, y1, flip_y=False):
    """Apply the extraction crop formula and return the numpy crop."""
    pix_h, pix_w = img.shape[:2]
    sx0 = int(np.clip(int(x0 - 1), 0, pix_w))
    sx1 = int(np.clip(int(x1 + 1), 0, pix_w))
    if flip_y:
        sy0 = int(np.clip(int(pix_h - y1 - 1), 0, pix_h))
        sy1 = int(np.clip(int(pix_h - y0 + 1), 0, pix_h))
    else:
        sy0 = int(np.clip(int(y0 - 1), 0, pix_h))
        sy1 = int(np.clip(int(y1 + 1), 0, pix_h))
    return img[sy0:sy1, sx0:sx1]


def _red_pixel_count(crop_bgr):
    return int(np.sum(np.all(crop_bgr == [0, 0, 255], axis=2)))


class TestFigureCropCoordinates(unittest.TestCase):

    def setUp(self):
        self.img = _make_page_image()
        # DocLayout detection matching the red square (y from top)
        self.bbox = (80.0, 20.0, 180.0, 80.0)  # x0, y0, x1, y1

    def test_correct_formula_captures_target(self):
        """No y-flip: crop must contain red pixels from the target region."""
        crop = _crop(self.img, *self.bbox, flip_y=False)
        self.assertGreater(_red_pixel_count(crop), 0,
                           "Correct crop should contain red pixels")

    def test_flipped_formula_misses_target(self):
        """Old y-flip formula crops the wrong region (no red pixels)."""
        crop = _crop(self.img, *self.bbox, flip_y=True)
        self.assertEqual(_red_pixel_count(crop), 0,
                         "Flipped crop should NOT contain red pixels")

    def test_crop_covers_full_bbox(self):
        """Crop dimensions must encompass the bounding box (with 1-px margin)."""
        x0, y0, x1, y1 = self.bbox
        crop = _crop(self.img, *self.bbox, flip_y=False)
        expected_h = int(y1 - y0) + 2  # +1 each side margin
        expected_w = int(x1 - x0) + 2
        self.assertGreaterEqual(crop.shape[0], expected_h - 1)
        self.assertGreaterEqual(crop.shape[1], expected_w - 1)

    def test_crop_does_not_exceed_image_bounds(self):
        """Clip logic must prevent out-of-bounds slicing even at image edges."""
        pix_h, pix_w = self.img.shape[:2]
        # Detection touching the right and bottom edges
        edge_bbox = (pix_w - 5.0, pix_h - 5.0, pix_w + 10.0, pix_h + 10.0)
        crop = _crop(self.img, *edge_bbox, flip_y=False)
        self.assertGreater(crop.size, 0, "Edge crop should still produce a non-empty array")
        self.assertLessEqual(crop.shape[1], pix_w)
        self.assertLessEqual(crop.shape[0], pix_h)

    def test_saved_png_contains_target_color(self):
        """End-to-end: BGR crop → RGB → saved PNG → loaded array contains red."""
        from PIL import Image

        crop_bgr = _crop(self.img, *self.bbox, flip_y=False)
        crop_rgb = crop_bgr[:, :, ::-1]

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            out_path = f.name
        try:
            Image.fromarray(crop_rgb.astype("uint8"), "RGB").save(out_path)
            loaded = np.array(Image.open(out_path))
            red_pixels = int(np.sum(np.all(loaded == [255, 0, 0], axis=2)))
            self.assertGreater(red_pixels, 0,
                               "Saved PNG should contain RGB red pixels")
        finally:
            os.unlink(out_path)


if __name__ == "__main__":
    unittest.main()
