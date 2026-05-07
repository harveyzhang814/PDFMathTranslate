# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run all tests
python3 -m pytest test/ -v

# Run a single test file
python3 -m pytest test/test_export_word.py -v

# Run a single test case
python3 -m pytest test/test_caption_pairing.py::TestPairFigureCaption::test_caption_below_figure_is_paired -v

# Install project (required before running tests)
pip3 install -e .
pip3 install pytest python-docx

# Translate a PDF (CLI)
pdf2zh document.pdf -s google -o ./output

# Word export (uses --extract-elements internally)
pdf2zh document.pdf --word -o ./output

# Lint
flake8 pdf2zh/
```

## Architecture

This is a fork of PDFMathTranslate. The core pipeline is:

```
CLI (pdf2zh.py)
  └─► KernelRegistry  ──► LegacyKernel ("fast")   ──► high_level.translate()
                      └──► PreciseKernel ("precise") ──► pdf2zh_next subprocess
```

**Translation pipeline (`high_level.py`):**

1. `translate()` — entry point; handles file I/O, doc/docx→PDF conversion, then calls `translate_stream()`
2. `translate_stream()` — sets up fonts, opens the pymupdf document, calls `translate_patch()`
3. `translate_patch()` — the core page-by-page loop:
   - Runs the DocLayout ONNX model on each page pixmap to detect regions (figure, table, figure_caption, abandon, text, etc.)
   - Builds a `layout` array (h×w int) mapping each pixel to a region class — class 0 = "masked/don't translate"
   - Collects figure/caption boxes; extracts caption text via pymupdf `get_text(clip=...)`
   - Runs `PDFPageInterpreterEx` → `TranslateConverter.receive_layout()` which parses characters, detects math fonts, batches paragraphs, translates them, and re-renders PDF ops
   - After all pages: calls `pair_figure_caption()` + `build_element_manifest()` if `extract_elements=True`
4. `translate_to_word()` — calls `translate()` with `extract_elements=True`, then calls `export_pdf_to_word()`

**Coordinate systems — important:**
- The DocLayout model outputs bounding boxes in **screen pixel coordinates** (y from top, same origin as the pixmap)
- The `layout` array is built with **flipped y** (`h - y`) to match PDF/pdfminer coordinates (y from bottom)
- pymupdf `get_text(clip=...)` uses **y from top** (same as pixmap), so caption bbox pixel coords map directly with scale `sx = page.rect.width / pix.width`
- `LTChar` positions from pdfminer use **y from bottom**

**`converter.py` — `TranslateConverter.receive_layout()`:**
- Iterates `LTChar` objects; each character is looked up in the `layout` array to determine if it's in a masked region (cls=0 → render as math/formula placeholder `{vN}`)
- Builds paragraph stacks (`sstk`, `pstk`), translates in parallel via `ThreadPoolExecutor`, then re-renders translated text into PDF stream ops
- Column-aware reordering: uses `_page_gutter_x0` (set in `begin_page`) to bucket paragraphs left/right before translation

**Fork-specific modules:**

| Module | Purpose |
|---|---|
| `text_order.py` | Column layout detection (`detect_column_layout`) and reading-order sort (`sort_text_blocks_by_layout`) |
| `caption_pairing.py` | Proximity-based figure↔caption matching; writes `elements/manifest.json` |
| `export_word.py` | Builds `.docx` from translated mono.pdf + extracted element images |
| `converter_docx.py` | Converts `.doc`/`.docx` input files to PDF before translation |

**Kernel system (`pdf2zh/kernel/`):**
- `KernelRegistry` — thread-safe singleton; default kernel is `"fast"` (LegacyKernel)
- `LegacyKernel` — wraps `high_level.translate()`; always available
- `PreciseKernel` — runs `pdf2zh_next` in an isolated venv subprocess (`kernel/PDFMathTranslate-next.git`); only available if submodule is initialized
- `v2_bridge.py` — maps `TranslateRequest` fields to v2 CLI args and env vars

## Test Index

| Feature | Source | Test file |
|---|---|---|
| Translation cache | `pdf2zh/cache.py` | `test/test_cache.py` |
| CLI entry / version flag | `pdf2zh/pdf2zh.py` | `test/test_cli.py` |
| PDF converter (char rendering, paragraph parsing, formulas) | `pdf2zh/converter.py` | `test/test_converter.py` |
| DocLayout ONNX model (predict, resize, scale) | `pdf2zh/doclayout.py` | `test/test_doclayout.py` |
| Word export (reading-order sort, multi-page handling) | `pdf2zh/export_word.py` | `test/test_export_word.py` |
| Figure–caption proximity pairing; manifest generation | `pdf2zh/caption_pairing.py` | `test/test_caption_pairing.py` |
| Kernel registry, CLI→kernel routing, translation pipeline | `pdf2zh/kernel/` | `test/test_kernel.py` |
| Translators (cache, OpenAI-like, Ollama) | `pdf2zh/translator.py` | `test/test_translator.py` |

**No tests yet:** `text_order.py`, `high_level.py` (integration), `converter_docx.py`
