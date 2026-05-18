# Markdown Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `--markdown` CLI flag that translates a PDF and exports the result as an Obsidian-compatible Markdown document with images in a sibling `images/` folder.

**Architecture:** New standalone module `pdf2zh/export_markdown.py` mirrors the structure of `export_word.py` (extract text blocks → sort by reading order → interleave images with captions) but writes plain Markdown instead of `.docx`. A new `translate_to_markdown()` in `high_level.py` orchestrates the pipeline identical to `translate_to_word()`. A new `--markdown` flag in `pdf2zh.py` routes to it.

**Tech Stack:** pymupdf (text block extraction), numpy (avg width for column detection), `pdf2zh.text_order.sort_text_blocks_by_layout` (reading-order sort), Python stdlib `shutil`/`pathlib` (file I/O).

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `pdf2zh/export_markdown.py` | Core exporter: PDF → Markdown + image copy |
| Modify | `pdf2zh/high_level.py` | Add `translate_to_markdown()` |
| Modify | `pdf2zh/pdf2zh.py` | Add `--markdown` arg + dispatch |
| Create | `test/test_export_markdown.py` | Unit + integration tests |

---

## Task 1: Helper functions + tests

**Files:**
- Create: `test/test_export_markdown.py`
- Create: `pdf2zh/export_markdown.py` (helpers only, no main export function yet)

### Step 1.1 — Write failing tests for helper functions

Create `test/test_export_markdown.py`:

```python
import unittest


class TestParseElemFilename(unittest.TestCase):
    def test_figure_filename(self):
        from pdf2zh.export_markdown import _parse_elem_filename
        self.assertEqual(
            _parse_elem_filename("p2_figure_001.png"),
            {"type": "figure", "idx": 1},
        )

    def test_table_filename(self):
        from pdf2zh.export_markdown import _parse_elem_filename
        self.assertEqual(
            _parse_elem_filename("p10_table_003.png"),
            {"type": "table", "idx": 3},
        )

    def test_invalid_filename_returns_none(self):
        from pdf2zh.export_markdown import _parse_elem_filename
        self.assertIsNone(_parse_elem_filename("invalid.png"))
        self.assertIsNone(_parse_elem_filename("figure_001.png"))


class TestMakeCaptionLabel(unittest.TestCase):
    def test_figure_label(self):
        from pdf2zh.export_markdown import _make_caption_label
        self.assertEqual(_make_caption_label("p1_figure_001.png"), "Figure 1")

    def test_table_label(self):
        from pdf2zh.export_markdown import _make_caption_label
        self.assertEqual(_make_caption_label("p3_table_002.png"), "Table 2")

    def test_unknown_type_capitalized(self):
        from pdf2zh.export_markdown import _make_caption_label
        self.assertEqual(_make_caption_label("p1_chart_001.png"), "Chart 1")

    def test_invalid_filename_fallback(self):
        from pdf2zh.export_markdown import _make_caption_label
        self.assertEqual(_make_caption_label("weird.png"), "weird")


class TestIsCaption(unittest.TestCase):
    def test_figure_keyword(self):
        from pdf2zh.export_markdown import _is_caption
        self.assertTrue(_is_caption("Figure 1 shows the results"))
        self.assertTrue(_is_caption("fig. 2 comparison"))

    def test_table_keyword(self):
        from pdf2zh.export_markdown import _is_caption
        self.assertTrue(_is_caption("Table 3 summary statistics"))

    def test_cjk_caption(self):
        from pdf2zh.export_markdown import _is_caption
        self.assertTrue(_is_caption("图1 实验结果"))
        self.assertTrue(_is_caption("表2 数据统计"))

    def test_long_text_not_caption(self):
        from pdf2zh.export_markdown import _is_caption
        self.assertFalse(_is_caption("figure " + "x" * 295))

    def test_period_ending_not_caption(self):
        from pdf2zh.export_markdown import _is_caption
        self.assertFalse(_is_caption("This figure shows the result."))

    def test_body_text_without_keywords(self):
        from pdf2zh.export_markdown import _is_caption
        self.assertFalse(_is_caption("The proposed method achieves state-of-the-art"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 1.2 — Run tests to verify they fail**

```bash
python3 -m pytest test/test_export_markdown.py -v
```

Expected: `ModuleNotFoundError: No module named 'pdf2zh.export_markdown'`

- [ ] **Step 1.3 — Create `pdf2zh/export_markdown.py` with helpers**

```python
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
```

- [ ] **Step 1.4 — Run tests to verify they pass**

```bash
python3 -m pytest test/test_export_markdown.py -v
```

Expected: All 12 tests pass.

- [ ] **Step 1.5 — Commit**

```bash
git add pdf2zh/export_markdown.py test/test_export_markdown.py
git commit -m "feat: scaffold export_markdown with helper functions and tests"
```

---

## Task 2: Implement `export_pdf_to_markdown()`

**Files:**
- Modify: `pdf2zh/export_markdown.py` (add main export function)
- Modify: `test/test_export_markdown.py` (add integration tests)

- [ ] **Step 2.1 — Add integration tests**

Append to `test/test_export_markdown.py`:

```python
import os
import shutil
import tempfile


class TestExportPdfToMarkdown(unittest.TestCase):
    PDF_PLAIN = os.path.join(
        os.path.dirname(__file__), "file", "translate.cli.plain.text.pdf"
    )
    PDF_FIGURE = os.path.join(
        os.path.dirname(__file__), "file", "translate.cli.text.with.figure.pdf"
    )

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _fake_elem_dir(self, filenames):
        """Create a temp elem_dir with stub PNG files."""
        elem_dir = os.path.join(self.tmpdir, "elems")
        elements = os.path.join(elem_dir, "elements")
        os.makedirs(elements)
        for fname in filenames:
            with open(os.path.join(elements, fname), "wb") as f:
                # Minimal 1x1 PNG (67 bytes)
                f.write(
                    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
                    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
                    b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18"
                    b"\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
                )
        return elem_dir

    def test_creates_md_file(self):
        from pdf2zh.export_markdown import export_pdf_to_markdown
        output_dir = os.path.join(self.tmpdir, "out")
        md_path = export_pdf_to_markdown(self.PDF_PLAIN, None, output_dir)
        self.assertTrue(os.path.isfile(md_path))
        self.assertTrue(md_path.endswith(".md"))

    def test_creates_images_directory(self):
        from pdf2zh.export_markdown import export_pdf_to_markdown
        output_dir = os.path.join(self.tmpdir, "out")
        export_pdf_to_markdown(self.PDF_PLAIN, None, output_dir)
        self.assertTrue(os.path.isdir(os.path.join(output_dir, "images")))

    def test_copies_images_to_images_dir(self):
        from pdf2zh.export_markdown import export_pdf_to_markdown
        elem_dir = self._fake_elem_dir(["p1_figure_001.png"])
        output_dir = os.path.join(self.tmpdir, "out")
        export_pdf_to_markdown(self.PDF_PLAIN, elem_dir, output_dir)
        self.assertTrue(
            os.path.isfile(os.path.join(output_dir, "images", "p1_figure_001.png"))
        )

    def test_image_wikilink_appears_in_markdown(self):
        from pdf2zh.export_markdown import export_pdf_to_markdown
        elem_dir = self._fake_elem_dir(["p1_figure_001.png"])
        output_dir = os.path.join(self.tmpdir, "out")
        md_path = export_pdf_to_markdown(self.PDF_PLAIN, elem_dir, output_dir)
        content = open(md_path, encoding="utf-8").read()
        self.assertIn("![[images/p1_figure_001.png]]", content)

    def test_page_separator_for_multipage_pdf(self):
        import pymupdf
        from pdf2zh.export_markdown import export_pdf_to_markdown
        doc = pymupdf.open(self.PDF_PLAIN)
        page_count = doc.page_count
        doc.close()
        if page_count < 2:
            self.skipTest("PDF has only one page; separator test requires 2+")
        output_dir = os.path.join(self.tmpdir, "out")
        md_path = export_pdf_to_markdown(self.PDF_PLAIN, None, output_dir)
        content = open(md_path, encoding="utf-8").read()
        self.assertIn("\n---\n", content)

    def test_no_separator_on_first_page(self):
        from pdf2zh.export_markdown import export_pdf_to_markdown
        output_dir = os.path.join(self.tmpdir, "out")
        md_path = export_pdf_to_markdown(self.PDF_PLAIN, None, output_dir)
        content = open(md_path, encoding="utf-8").read()
        self.assertFalse(content.startswith("---"))
```

- [ ] **Step 2.2 — Run tests to verify they fail**

```bash
python3 -m pytest test/test_export_markdown.py::TestExportPdfToMarkdown -v
```

Expected: `AttributeError: module 'pdf2zh.export_markdown' has no attribute 'export_pdf_to_markdown'`

- [ ] **Step 2.3 — Implement `export_pdf_to_markdown()` in `pdf2zh/export_markdown.py`**

Append to `pdf2zh/export_markdown.py` (after the helpers):

```python
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
```

- [ ] **Step 2.4 — Run tests to verify they pass**

```bash
python3 -m pytest test/test_export_markdown.py -v
```

Expected: All tests pass (skip possible for single-page PDF separator test).

- [ ] **Step 2.5 — Commit**

```bash
git add pdf2zh/export_markdown.py test/test_export_markdown.py
git commit -m "feat: implement export_pdf_to_markdown with reading-order sort and Obsidian links"
```

---

## Task 3: Add `translate_to_markdown()` to `high_level.py`

**Files:**
- Modify: `pdf2zh/high_level.py` (add function after `translate_to_word`)
- Modify: `test/test_export_markdown.py` (add import/signature test)

- [ ] **Step 3.1 — Write a failing import test**

Append to `test/test_export_markdown.py`:

```python
class TestTranslateToMarkdownSignature(unittest.TestCase):
    def test_function_exists_and_is_callable(self):
        from pdf2zh.high_level import translate_to_markdown
        import inspect
        sig = inspect.signature(translate_to_markdown)
        self.assertIn("files", sig.parameters)
        self.assertIn("output", sig.parameters)
        self.assertIn("lang_out", sig.parameters)
```

- [ ] **Step 3.2 — Run test to verify it fails**

```bash
python3 -m pytest test/test_export_markdown.py::TestTranslateToMarkdownSignature -v
```

Expected: `ImportError: cannot import name 'translate_to_markdown'`

- [ ] **Step 3.3 — Add `translate_to_markdown()` to `pdf2zh/high_level.py`**

Add this import at the top of `high_level.py` (alongside the existing `export_pdf_to_word` import):

```python
from pdf2zh.export_markdown import export_pdf_to_markdown
```

Then append after the `translate_to_word` function (around line 554):

```python
def translate_to_markdown(
    files: List[str],
    output: str = "",
    lang_in: str = "en",
    lang_out: str = "zh",
    service: str = "google",
    thread: int = 0,
    model=None,
    pages: Optional[List[int]] = None,
    skip_subset_fonts: bool = True,
    **kwargs,
) -> str:
    """
    Translate PDF files and export as a Markdown document with Obsidian image links.

    Args:
        files: list of input PDF paths
        output: output directory (task folder created inside as <stem>/)
        lang_in: source language
        lang_out: target language
        service: translation service (e.g. "google", "ollama:gemma2:9b")
        thread: number of threads (0=auto)
        model: layout model (OnnxModel instance)
        pages: optional page list to translate

    Returns:
        Path to the generated .md file
    """
    import shutil as _shutil

    if not output:
        output = tempfile.mkdtemp(prefix="pdf2zh_markdown_")
    output_path = Path(output)
    output_path.mkdir(parents=True, exist_ok=True)

    elem_dir = tempfile.mkdtemp(prefix="pdf2zh_elem_")
    try:
        result = translate(
            files=files,
            output=str(output_path),
            lang_in=lang_in,
            lang_out=lang_out,
            service=service,
            thread=thread,
            model=model,
            pages=pages,
            extract_elements=True,
            elements_output_dir=elem_dir,
            skip_subset_fonts=skip_subset_fonts,
        )

        mono_pdf = result[0][0]
        stem = Path(mono_pdf).stem
        task_dir = str(output_path / stem)
        md_path = export_pdf_to_markdown(mono_pdf, elem_dir, task_dir, lang_out=lang_out)
    finally:
        _shutil.rmtree(elem_dir, ignore_errors=True)

    return md_path
```

- [ ] **Step 3.4 — Run tests to verify they pass**

```bash
python3 -m pytest test/test_export_markdown.py -v
```

Expected: All tests pass.

- [ ] **Step 3.5 — Commit**

```bash
git add pdf2zh/high_level.py test/test_export_markdown.py
git commit -m "feat: add translate_to_markdown() to high_level.py"
```

---

## Task 4: Add `--markdown` CLI flag

**Files:**
- Modify: `pdf2zh/pdf2zh.py` (add argument + dispatch block)
- Modify: `test/test_export_markdown.py` (add CLI parser test)

- [ ] **Step 4.1 — Write a failing CLI test**

Append to `test/test_export_markdown.py`:

```python
class TestMarkdownCliFlag(unittest.TestCase):
    def test_markdown_flag_is_registered(self):
        from pdf2zh.pdf2zh import create_parser
        parser = create_parser()
        # parse_args raises SystemExit on --help; test with known-good args
        args = parser.parse_args(["dummy.pdf", "--markdown"])
        self.assertTrue(args.markdown)

    def test_markdown_flag_defaults_false(self):
        from pdf2zh.pdf2zh import create_parser
        parser = create_parser()
        args = parser.parse_args(["dummy.pdf"])
        self.assertFalse(args.markdown)
```

- [ ] **Step 4.2 — Run test to verify it fails**

```bash
python3 -m pytest test/test_export_markdown.py::TestMarkdownCliFlag -v
```

Expected: `error: unrecognized arguments: --markdown`

- [ ] **Step 4.3 — Add `--markdown` argument and dispatch to `pdf2zh/pdf2zh.py`**

In `pdf2zh.py`, locate the block that adds `--word` (around line 217) and add immediately after it:

```python
    parse_params.add_argument(
        "--markdown",
        action="store_true",
        help="Export translated content as Markdown with images in images/ subfolder.",
    )
```

Locate the `if parsed_args.word:` dispatch block (around line 366) and add a parallel block immediately after its `return 0`:

```python
    if parsed_args.markdown:
        from pdf2zh.high_level import translate_to_markdown
        from pdf2zh.doclayout import OnnxModel

        for file in parsed_args.files:
            md_path = translate_to_markdown(
                files=[file],
                output=parsed_args.output or "",
                lang_in=parsed_args.lang_in,
                lang_out=parsed_args.lang_out,
                service=parsed_args.service,
                thread=parsed_args.thread,
                model=ModelInstance.value,
                pages=parsed_args.pages,
            )
            print(f"Markdown saved: {md_path}")
        return 0
```

- [ ] **Step 4.4 — Run all tests to verify everything passes**

```bash
python3 -m pytest test/ -v --ignore=test/test_converter.py
```

Expected: All tests pass (ignoring the 4 pre-existing `test_converter.py` failures).

- [ ] **Step 4.5 — Commit**

```bash
git add pdf2zh/pdf2zh.py test/test_export_markdown.py
git commit -m "feat: add --markdown CLI flag for Markdown export"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] New `pdf2zh/export_markdown.py` → Tasks 1 & 2
- [x] Output structure `<stem>/` + `images/` → Task 2 (`export_pdf_to_markdown` receives `output_dir = output_path / stem`)
- [x] Obsidian wikilinks `![[images/...]]` → Task 2 step 2.3
- [x] `---` page separators → Task 2 step 2.3
- [x] Flat paragraphs, no heading detection → confirmed in Task 2 (no heading logic)
- [x] Caption → image + italic caption → Task 2 step 2.3
- [x] `translate_to_markdown()` in `high_level.py` → Task 3
- [x] `--markdown` CLI flag → Task 4
- [x] Images copied from elem_dir to images/ → Task 2 step 2.3
- [x] `sort_text_blocks_by_layout` with correct y-flip → Task 2 step 2.3

**Placeholder scan:** No TBDs, no TODOs, all code blocks are complete.

**Type consistency:**
- `_parse_elem_filename` returns `Optional[dict]` with keys `type`, `idx` — used consistently in Tasks 1 & 2
- `export_pdf_to_markdown(pdf_mono_path, elem_dir, output_dir, lang_out)` — signature matches in Task 2 (implementation), Task 3 (call site), and tests
- `translate_to_markdown` signature in Task 3 matches Task 4 call site
