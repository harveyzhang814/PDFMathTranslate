# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
pip3 install -e . && pip3 install pytest python-docx   # first-time setup

python3 -m pytest test/ -v                             # unit tests (e2e excluded)
python3 -m pytest test/e2e/ -v -m e2e                 # e2e (slow; needs network + ONNX)

pdf2zh document.pdf -s google -o ./output             # translate PDF
pdf2zh document.pdf --word -o ./output                # Word export
pdf2zh document.pdf --markdown -o ./output            # Markdown export
flake8 pdf2zh/
```

## Architecture

This is a fork of PDFMathTranslate. Core pipeline:

```
CLI (pdf2zh.py)
  └─► KernelRegistry  ──► LegacyKernel ("fast")    ──► high_level.translate()
                      └──► PreciseKernel ("precise") ──► pdf2zh_next subprocess
```

**Translation pipeline (`high_level.py`):**

1. `translate()` — file I/O, doc/docx→PDF, calls `translate_stream()`
2. `translate_stream()` — font setup, opens pymupdf doc, calls `translate_patch()`
3. `translate_patch()` — page-by-page loop:
   - DocLayout ONNX model → region detection (figure/table/caption/abandon/text…)
   - Builds `layout` array (h×w int); class 0 = masked/don't translate
   - `PDFPageInterpreterEx` → `TranslateConverter.receive_layout()` → parse chars, detect math, batch+translate paragraphs, re-render PDF ops
   - After all pages: `pair_figure_caption()` + `build_element_manifest()` if `extract_elements=True`
4. `translate_to_word()` — `translate(extract_elements=True)` → `export_pdf_to_word()`

**Coordinate systems (critical):**
- DocLayout boxes → **screen pixels** (y from top, pixmap origin)
- `layout` array → **flipped y** (`h - y`) to match pdfminer (y from bottom)
- pymupdf `get_text(clip=...)` → y from top; scale with `sx = page.rect.width / pix.width`
- `LTChar` from pdfminer → y from bottom

**`converter.py` — `TranslateConverter.receive_layout()`:**
- `LTChar` → `layout` lookup → masked chars become `{vN}` formula placeholders
- `ThreadPoolExecutor` parallel translation; column-aware reorder via `_page_gutter_x0`

**Fork-specific modules:** `text_order.py` (column detection + reading-order sort), `caption_pairing.py` (figure↔caption matching → `elements/manifest.json`), `export_word.py`, `export_markdown.py` (Obsidian wikilinks), `converter_docx.py` (doc/docx→PDF), `debackground.py` (scanned-PDF white-rect injection)

**Kernel system (`pdf2zh/kernel/`):** `KernelRegistry` singleton; `LegacyKernel` wraps `high_level`; `PreciseKernel` runs `pdf2zh_next` subprocess; `v2_bridge.py` maps `TranslateRequest` → v2 CLI args.

## Tests

Unit tests mirror source: `test/test_<module>.py`. See test file headers for coverage details.
No tests yet: `text_order.py`, `high_level.py` (integration), `converter_docx.py`.

E2E tests in `test/e2e/` — `fixtures/` (input PDFs), `expected/` (JSON baselines, auto-generated on first run), `output/` (not committed). Baselines and fixture PDFs can be committed.
