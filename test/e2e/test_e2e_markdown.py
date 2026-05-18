"""
E2E test: full translate + Markdown export pipeline on a real PDF fixture.

Run with:
    python3 -m pytest test/e2e/ -v -m e2e

First run creates test/e2e/expected/markdown_3pages_baseline.json;
subsequent runs compare line count within ±20%.
"""
import json
import shutil
import tempfile
from pathlib import Path

import pytest

FIXTURE_PDF = Path(__file__).parent / "fixtures" / "S0894731722001407.pdf"
EXPECTED_DIR = Path(__file__).parent / "expected"
OUTPUT_DIR = Path(__file__).parent / "output" / "markdown_3pages"
BASELINE_FILE = EXPECTED_DIR / "markdown_3pages_baseline.json"

# Pages 3-5 (0-indexed): PDF pages 4-6, which contain figures
PAGES = [3, 4, 5]
TOLERANCE = 0.20


@pytest.fixture(scope="module")
def onnx_model():
    from pdf2zh.doclayout import OnnxModel
    return OnnxModel.load_available()


@pytest.fixture(scope="module")
def md_path(onnx_model):
    from pdf2zh.doclayout import ModelInstance
    from pdf2zh.export_markdown import export_pdf_to_markdown
    from pdf2zh.kernel import KernelRegistry
    from pdf2zh.kernel.protocol import TranslateRequest

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ModelInstance.value = onnx_model

    KernelRegistry.switch("fast")
    kernel = KernelRegistry.get()

    elem_dir = tempfile.mkdtemp(prefix="pdf2zh_e2e_elem_")
    try:
        request = TranslateRequest(
            files=[str(FIXTURE_PDF)],
            output=str(OUTPUT_DIR),
            lang_in="en",
            lang_out="zh",
            service="google",
            pages=PAGES,
            extract_elements=True,
            elements_output_dir=elem_dir,
        )
        results = kernel.translate(request)
        mono = Path(results[0].mono_pdf)
        task_dir = str(OUTPUT_DIR / mono.stem)
        md = export_pdf_to_markdown(str(mono), elem_dir, task_dir, lang_out="zh")
    finally:
        shutil.rmtree(elem_dir, ignore_errors=True)

    return Path(md)


@pytest.mark.e2e
class TestMarkdownExportE2E:
    def test_md_file_exists(self, md_path):
        assert md_path.exists(), f"Expected .md at {md_path}"
        assert md_path.suffix == ".md"

    def test_images_dir_exists(self, md_path):
        images_dir = md_path.parent / "images"
        assert images_dir.is_dir(), f"Expected images/ at {images_dir}"

    def test_md_has_content(self, md_path):
        content = md_path.read_text(encoding="utf-8")
        assert len(content.strip()) > 100, "Markdown file suspiciously short"

    def test_md_has_paragraphs(self, md_path):
        content = md_path.read_text(encoding="utf-8")
        non_empty_lines = [l for l in content.splitlines() if l.strip() and l.strip() != "---"]
        assert len(non_empty_lines) >= 5, f"Too few content lines: {len(non_empty_lines)}"

    def test_md_has_image_wikilinks(self, md_path):
        """Pages 4-6 of this paper contain figures; at least one wikilink expected."""
        content = md_path.read_text(encoding="utf-8")
        images_dir = md_path.parent / "images"
        png_count = len(list(images_dir.glob("*.png"))) if images_dir.is_dir() else 0
        if png_count == 0:
            pytest.skip("No images extracted; wikilink check skipped")
        assert "![[images/" in content, "No Obsidian wikilinks found despite extracted images"

    def test_page_separators(self, md_path):
        content = md_path.read_text(encoding="utf-8")
        # 3 pages → at least 2 separators (between page 1-2 and 2-3)
        assert content.count("\n---\n") >= 2, (
            f"Expected ≥2 page separators, found {content.count(chr(10) + '---' + chr(10))}"
        )

    def test_structural_regression(self, md_path):
        """Non-empty line count must stay within ±20% of the saved baseline."""
        content = md_path.read_text(encoding="utf-8")
        non_empty = [l for l in content.splitlines() if l.strip()]
        current = {"line_count": len(non_empty)}

        if not BASELINE_FILE.exists():
            BASELINE_FILE.parent.mkdir(parents=True, exist_ok=True)
            BASELINE_FILE.write_text(json.dumps(current, indent=2))
            return  # First run creates baseline; test trivially passes.

        baseline = json.loads(BASELINE_FILE.read_text())
        for key, val in current.items():
            expected = baseline[key]
            lo = expected * (1 - TOLERANCE)
            hi = expected * (1 + TOLERANCE)
            assert lo <= val <= hi, (
                f"{key}: got {val}, baseline {expected} (±{TOLERANCE:.0%} → [{lo:.0f}, {hi:.0f}])"
            )
