"""Functions that can be used for the most common use-cases for pdf2zh.six"""

import asyncio
import io
import os
import re
import shutil
import sys
import tempfile
import logging
from asyncio import CancelledError
from pathlib import Path
from string import Template
from typing import Any, BinaryIO, List, Optional, Dict

import numpy as np
import requests
import tqdm

from pdf2zh.converter_docx import convert_to_pdf, is_convertible
from pdf2zh.export_word import export_pdf_to_word
from pdf2zh.export_markdown import export_pdf_to_markdown
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfexceptions import PDFValueError
from pdfminer.pdfinterp import PDFResourceManager
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfparser import PDFParser
from pymupdf import Document, Font, Rect as MuRect

from pdf2zh.converter import TranslateConverter
from pdf2zh.doclayout import OnnxModel
from pdf2zh.pdfinterp import PDFPageInterpreterEx

from pdf2zh.config import ConfigManager
from babeldoc.assets.assets import get_font_and_metadata

NOTO_NAME = "noto"

logger = logging.getLogger(__name__)

noto_list = [
    "am",  # Amharic
    "ar",  # Arabic
    "bn",  # Bengali
    "bg",  # Bulgarian
    "chr",  # Cherokee
    "el",  # Greek
    "gu",  # Gujarati
    "iw",  # Hebrew
    "hi",  # Hindi
    "kn",  # Kannada
    "ml",  # Malayalam
    "mr",  # Marathi
    "ru",  # Russian
    "sr",  # Serbian
    "ta",  # Tamil
    "te",  # Telugu
    "th",  # Thai
    "ur",  # Urdu
    "uk",  # Ukrainian
]


def check_files(files: List[str]) -> List[str]:
    files = [
        f for f in files if not f.startswith("http://")
    ]  # exclude online files, http
    files = [
        f for f in files if not f.startswith("https://")
    ]  # exclude online files, https
    missing_files = [file for file in files if not os.path.exists(file)]
    return missing_files


def translate_patch(
    inf: BinaryIO,
    pages: Optional[list[int]] = None,
    vfont: str = "",
    vchar: str = "",
    thread: int = 0,
    doc_zh: Document = None,
    lang_in: str = "",
    lang_out: str = "",
    service: str = "",
    noto_name: str = "",
    noto: Font = None,
    callback: object = None,
    cancellation_event: asyncio.Event = None,
    model: OnnxModel = None,
    envs: Dict = None,
    prompt: Template = None,
    ignore_cache: bool = False,
    extract_elements: bool = False,
    elements_output_dir: str = None,
    **kwarg: Any,
) -> None:
    rsrcmgr = PDFResourceManager()
    layout = {}
    device = TranslateConverter(
        rsrcmgr,
        vfont,
        vchar,
        thread,
        layout,
        lang_in,
        lang_out,
        service,
        noto_name,
        noto,
        envs,
        prompt,
        ignore_cache,
    )

    assert device is not None
    obj_patch = {}
    interpreter = PDFPageInterpreterEx(rsrcmgr, device, obj_patch)
    if pages:
        total_pages = len(pages)
    else:
        total_pages = doc_zh.page_count

    all_figure_boxes: list = []
    all_table_page_coords: list = []  # table bboxes in pymupdf page coords for Markdown export
    all_caption_boxes: list = []
    all_figure_page_coords: list = []  # figure bboxes in pymupdf page coords for Word export

    parser = PDFParser(inf)
    doc = PDFDocument(parser)
    with tqdm.tqdm(total=total_pages) as progress:
        for pageno, page in enumerate(PDFPage.create_pages(doc)):
            if cancellation_event and cancellation_event.is_set():
                raise CancelledError("task cancelled")
            if pages and (pageno not in pages):
                continue
            progress.update()
            if callback:
                callback(progress)
            page.pageno = pageno
            pix = doc_zh[page.pageno].get_pixmap()
            image = np.frombuffer(pix.samples, np.uint8).reshape(
                pix.height, pix.width, 3
            )[:, :, ::-1]
            page_layout = model.predict(image, imgsz=int(pix.height / 32) * 32)[0]

            # ---- Collect element boxes for layout analysis and caption pairing ----
            figure_boxes = []
            table_boxes = []
            caption_data = {}  # {(pageno, type, idx): text}
            elem_counter = {"figure": 0, "table": 0}

            page_caption_boxes = []
            for d in page_layout.boxes:
                cls_name = page_layout.names[int(d.cls)]
                if cls_name == "table":
                    x0, y0, x1, y1 = d.xyxy.squeeze()
                    table_boxes.append({"x0": float(x0), "y0": float(y0), "x1": float(x1), "y1": float(y1)})
                elif cls_name == "figure":
                    elem_counter["figure"] += 1
                    idx = elem_counter["figure"]
                    x0, y0, x1, y1 = d.xyxy.squeeze()
                    figure_boxes.append({"x0": float(x0), "y0": float(y0), "x1": float(x1), "y1": float(y1), "idx": idx, "pageno": pageno})
                elif cls_name == "figure_caption":
                    x0, y0, x1, y1 = d.xyxy.squeeze()
                    page_caption_boxes.append({"x0": float(x0), "y0": float(y0), "x1": float(x1), "y1": float(y1), "pageno": pageno})

            # Compute pixel→page scale and collect caption text + figure/table page coords
            if figure_boxes or table_boxes or page_caption_boxes:
                mupdf_page = doc_zh[pageno]
                sx = mupdf_page.rect.width / pix.width if pix.width else 1.0
                sy = mupdf_page.rect.height / pix.height if pix.height else 1.0

                for cap in page_caption_boxes:
                    clip = MuRect(cap["x0"] * sx, cap["y0"] * sy, cap["x1"] * sx, cap["y1"] * sy)
                    cap["text"] = mupdf_page.get_text("text", clip=clip).strip()
                all_caption_boxes.extend(page_caption_boxes)

                for fig in figure_boxes:
                    all_figure_page_coords.append({
                        "pageno": fig["pageno"],
                        "idx": fig["idx"],
                        "image_file": f"p{fig['pageno'] + 1}_figure_{fig['idx']:03d}.png",
                        "x0": fig["x0"] * sx,
                        "y0": fig["y0"] * sy,
                        "x1": fig["x1"] * sx,
                        "y1": fig["y1"] * sy,
                    })

                for i, tbl in enumerate(table_boxes):
                    all_table_page_coords.append({
                        "pageno": pageno,
                        "idx": i + 1,
                        "image_file": f"p{pageno + 1}_table_{i + 1:03d}.png",
                        "x0": tbl["x0"] * sx,
                        "y0": tbl["y0"] * sy,
                        "x1": tbl["x1"] * sx,
                        "y1": tbl["y1"] * sy,
                    })

            all_figure_boxes.extend(figure_boxes)


            # ---- Extract figures and tables as separate images ----
            if extract_elements and elements_output_dir:
                from PIL import Image
                elem_dir = os.path.join(elements_output_dir, "elements")
                os.makedirs(elem_dir, exist_ok=True)
                extract_counter = {"figure": 0, "table": 0}
                pix_h, pix_w = pix.height, pix.width
                img_h, img_w = image.shape[:2]
                assert pix_h == img_h and pix_w == img_w
                for d in page_layout.boxes:
                    cls_name = page_layout.names[int(d.cls)]
                    if cls_name not in ("figure", "table"):
                        continue
                    x0, y0, x1, y1 = d.xyxy.squeeze()
                    # DocLayout xyxy and numpy image both use y=0 at top; no flip needed.
                    slice_x0 = int(np.clip(int(x0 - 1), 0, pix_w))
                    slice_x1 = int(np.clip(int(x1 + 1), 0, pix_w))
                    slice_y0 = int(np.clip(int(y0 - 1), 0, pix_h))
                    slice_y1 = int(np.clip(int(y1 + 1), 0, pix_h))
                    if slice_x1 <= slice_x0 or slice_y1 <= slice_y0:
                        continue
                    extract_counter[cls_name] += 1
                    crop_bgr = image[slice_y0:slice_y1, slice_x0:slice_x1]
                    crop_rgb = crop_bgr[:, :, ::-1]
                    pil_img = Image.fromarray(crop_rgb.astype("uint8"), "RGB")
                    fname = f"p{pageno+1}_{cls_name}_{extract_counter[cls_name]:03d}.png"
                    pil_img.save(os.path.join(elem_dir, fname))

            # kdtree 是不可能 kdtree 的，不如直接渲染成图片，用空间换时间
            box = np.ones((pix.height, pix.width))
            h, w = box.shape
            vcls = ["abandon", "figure", "table", "isolate_formula", "formula_caption"]
            for i, d in enumerate(page_layout.boxes):
                if page_layout.names[int(d.cls)] not in vcls:
                    x0, y0, x1, y1 = d.xyxy.squeeze()
                    x0, y0, x1, y1 = (
                        np.clip(int(x0 - 1), 0, w - 1),
                        np.clip(int(h - y1 - 1), 0, h - 1),
                        np.clip(int(x1 + 1), 0, w - 1),
                        np.clip(int(h - y0 + 1), 0, h - 1),
                    )
                    box[y0:y1, x0:x1] = i + 2
            for i, d in enumerate(page_layout.boxes):
                if page_layout.names[int(d.cls)] in vcls:
                    x0, y0, x1, y1 = d.xyxy.squeeze()
                    x0, y0, x1, y1 = (
                        np.clip(int(x0 - 1), 0, w - 1),
                        np.clip(int(h - y1 - 1), 0, h - 1),
                        np.clip(int(x1 + 1), 0, w - 1),
                        np.clip(int(h - y0 + 1), 0, h - 1),
                    )
                    box[y0:y1, x0:x1] = 0
            layout[page.pageno] = box
            # 新建一个 xref 存放新指令流
            page.page_xref = doc_zh.get_new_xref()  # hack 插入页面的新 xref
            doc_zh.update_object(page.page_xref, "<<>>")
            doc_zh.update_stream(page.page_xref, b"")
            doc_zh[page.pageno].set_contents(page.page_xref)
            interpreter.process_page(page)

    device.close()

    # Save figure bboxes in page coordinates for proximity-based Word export pairing
    if extract_elements and elements_output_dir and all_figure_page_coords:
        import json
        figures_json = os.path.join(elements_output_dir, "elements", "figures.json")
        os.makedirs(os.path.dirname(figures_json), exist_ok=True)
        with open(figures_json, "w", encoding="utf-8") as f:
            json.dump(all_figure_page_coords, f, indent=2)

    # Save table bboxes in page coordinates for Markdown export text-block deduplication
    if extract_elements and elements_output_dir and all_table_page_coords:
        import json
        tables_json = os.path.join(elements_output_dir, "elements", "tables.json")
        os.makedirs(os.path.dirname(tables_json), exist_ok=True)
        with open(tables_json, "w", encoding="utf-8") as f:
            json.dump(all_table_page_coords, f, indent=2)

    # Build element manifest after all pages are processed
    if extract_elements and elements_output_dir and all_figure_boxes:
        from pdf2zh.caption_pairing import pair_figure_caption, build_element_manifest
        pairings = pair_figure_caption(all_figure_boxes, all_caption_boxes)
        build_element_manifest(pairings, elements_output_dir)

    return obj_patch


def translate_stream(
    stream: bytes,
    pages: Optional[list[int]] = None,
    lang_in: str = "",
    lang_out: str = "",
    service: str = "",
    thread: int = 0,
    vfont: str = "",
    vchar: str = "",
    callback: object = None,
    cancellation_event: asyncio.Event = None,
    model: OnnxModel = None,
    envs: Dict = None,
    prompt: Template = None,
    skip_subset_fonts: bool = False,
    ignore_cache: bool = False,
    extract_elements: bool = False,
    elements_output_dir: str = None,
    **kwarg: Any,
):
    font_list = [("tiro", None)]

    font_path = download_remote_fonts(lang_out.lower())
    noto_name = NOTO_NAME
    noto = Font(noto_name, font_path)
    font_list.append((noto_name, font_path))

    doc_en = Document(stream=stream)
    stream = io.BytesIO()
    doc_en.save(stream)
    doc_zh = Document(stream=stream)
    page_count = doc_zh.page_count
    # font_list = [("GoNotoKurrent-Regular.ttf", font_path), ("tiro", None)]
    font_id = {}
    for page in doc_zh:
        for font in font_list:
            font_id[font[0]] = page.insert_font(font[0], font[1])
    xreflen = doc_zh.xref_length()
    for xref in range(1, xreflen):
        for label in ["Resources/", ""]:  # 可能是基于 xobj 的 res
            try:  # xref 读写可能出错
                font_res = doc_zh.xref_get_key(xref, f"{label}Font")
                target_key_prefix = f"{label}Font/"
                if font_res[0] == "xref":
                    resource_xref_id = re.search("(\\d+) 0 R", font_res[1]).group(1)
                    xref = int(resource_xref_id)
                    font_res = ("dict", doc_zh.xref_object(xref))
                    target_key_prefix = ""

                if font_res[0] == "dict":
                    for font in font_list:
                        target_key = f"{target_key_prefix}{font[0]}"
                        font_exist = doc_zh.xref_get_key(xref, target_key)
                        if font_exist[0] == "null":
                            doc_zh.xref_set_key(
                                xref,
                                target_key,
                                f"{font_id[font[0]]} 0 R",
                            )
            except Exception:
                pass

    fp = io.BytesIO()

    doc_zh.save(fp)
    obj_patch: dict = translate_patch(fp, **locals())

    for obj_id, ops_new in obj_patch.items():
        # ops_old=doc_en.xref_stream(obj_id)
        # print(obj_id)
        # print(ops_old)
        # print(ops_new.encode())
        doc_zh.update_stream(obj_id, ops_new.encode())

    doc_en.insert_file(doc_zh)
    for id in range(page_count):
        doc_en.move_page(page_count + id, id * 2 + 1)
    if not skip_subset_fonts:
        doc_zh.subset_fonts(fallback=True)
        doc_en.subset_fonts(fallback=True)
    mono_bytes = doc_zh.write(deflate=True, garbage=3, use_objstms=1)
    dual_bytes = doc_en.write(deflate=True, garbage=3, use_objstms=1)
    # Post-process: blank scan backgrounds for scanned PDFs (no-op for normal PDFs)
    from pdf2zh.debackground import debackground_scanned_pages
    mono_bytes = debackground_scanned_pages(mono_bytes)
    return mono_bytes, dual_bytes


def convert_to_pdfa(input_path, output_path):
    """
    Convert PDF to PDF/A format

    Args:
        input_path: Path to source PDF file
        output_path: Path to save PDF/A file
    """
    from pikepdf import Dictionary, Name, Pdf

    # Open the PDF file
    pdf = Pdf.open(input_path)

    # Add PDF/A conformance metadata
    metadata = {
        "pdfa_part": "2",
        "pdfa_conformance": "B",
        "title": pdf.docinfo.get("/Title", ""),
        "author": pdf.docinfo.get("/Author", ""),
        "creator": "PDF Math Translate",
    }

    with pdf.open_metadata() as meta:
        meta.load_from_docinfo(pdf.docinfo)
        meta["pdfaid:part"] = metadata["pdfa_part"]
        meta["pdfaid:conformance"] = metadata["pdfa_conformance"]

    # Create OutputIntent dictionary
    output_intent = Dictionary(
        {
            "/Type": Name("/OutputIntent"),
            "/S": Name("/GTS_PDFA1"),
            "/OutputConditionIdentifier": "sRGB IEC61966-2.1",
            "/RegistryName": "http://www.color.org",
            "/Info": "sRGB IEC61966-2.1",
        }
    )

    # Add output intent to PDF root
    if "/OutputIntents" not in pdf.Root:
        pdf.Root.OutputIntents = [output_intent]
    else:
        pdf.Root.OutputIntents.append(output_intent)

    # Save as PDF/A
    pdf.save(output_path, linearize=True)
    pdf.close()


def translate(
    files: list[str],
    output: str = "",
    pages: Optional[list[int]] = None,
    lang_in: str = "",
    lang_out: str = "",
    service: str = "",
    thread: int = 0,
    vfont: str = "",
    vchar: str = "",
    callback: object = None,
    compatible: bool = False,
    cancellation_event: asyncio.Event = None,
    model: OnnxModel = None,
    envs: Dict = None,
    prompt: Template = None,
    skip_subset_fonts: bool = False,
    ignore_cache: bool = False,
    extract_elements: bool = False,
    elements_output_dir: str = None,
    **kwarg: Any,
):
    if not files:
        raise PDFValueError("No files to process.")

    missing_files = check_files(files)

    if missing_files:
        print("The following files do not exist:", file=sys.stderr)
        for file in missing_files:
            print(f"  {file}", file=sys.stderr)
        raise PDFValueError("Some files do not exist.")

    result_files = []

    for file in files:
        if type(file) is str and (
            file.startswith("http://") or file.startswith("https://")
        ):
            print("Online files detected, downloading...")
            try:
                r = requests.get(file, allow_redirects=True)
                if r.status_code == 200:
                    with tempfile.NamedTemporaryFile(
                        suffix=".pdf", delete=False
                    ) as tmp_file:
                        print(f"Writing the file: {file}...")
                        tmp_file.write(r.content)
                        file = tmp_file.name
                else:
                    r.raise_for_status()
            except Exception as e:
                raise PDFValueError(
                    f"Errors occur in downloading the PDF file. Please check the link(s).\nError:\n{e}"
                )

        # Convert doc/docx to PDF if needed
        _converted_pdf = None
        if is_convertible(file):
            _converted_pdf = convert_to_pdf(file)
            filename = os.path.splitext(os.path.basename(file))[0]
            file = _converted_pdf
        else:
            filename = os.path.splitext(os.path.basename(file))[0]

        # If the commandline has specified converting to PDF/A format
        # --compatible / -cp
        if compatible:
            with tempfile.NamedTemporaryFile(
                suffix="-pdfa.pdf", delete=False
            ) as tmp_pdfa:
                print(f"Converting {file} to PDF/A format...")
                convert_to_pdfa(file, tmp_pdfa.name)
                doc_raw = open(tmp_pdfa.name, "rb")
                os.unlink(tmp_pdfa.name)
        else:
            doc_raw = open(file, "rb")
        s_raw = doc_raw.read()
        doc_raw.close()

        temp_dir = Path(tempfile.gettempdir())
        file_path = Path(file)
        try:
            if file_path.exists() and file_path.resolve().is_relative_to(
                temp_dir.resolve()
            ):
                file_path.unlink(missing_ok=True)
                logger.debug(f"Cleaned temp file: {file_path}")
        except Exception:
            logger.warning(f"Failed to clean temp file {file_path}", exc_info=True)

        s_mono, s_dual = translate_stream(
            s_raw,
            **locals(),
        )
        file_mono = Path(output) / f"{filename}-mono.pdf"
        file_dual = Path(output) / f"{filename}-dual.pdf"
        doc_mono = open(file_mono, "wb")
        doc_dual = open(file_dual, "wb")
        doc_mono.write(s_mono)
        doc_dual.write(s_dual)
        doc_mono.close()
        doc_dual.close()
        result_files.append((str(file_mono), str(file_dual)))

    return result_files


def download_remote_fonts(lang: str):
    lang = lang.lower()
    LANG_NAME_MAP = {
        **{la: "GoNotoKurrent-Regular.ttf" for la in noto_list},
        **{
            la: f"SourceHanSerif{region}-Regular.ttf"
            for region, langs in {
                "CN": ["zh-cn", "zh-hans", "zh"],
                "TW": ["zh-tw", "zh-hant"],
                "JP": ["ja"],
                "KR": ["ko"],
            }.items()
            for la in langs
        },
    }
    font_name = LANG_NAME_MAP.get(lang, "GoNotoKurrent-Regular.ttf")

    # docker
    font_path = ConfigManager.get("NOTO_FONT_PATH", Path("/app", font_name).as_posix())
    if not Path(font_path).exists():
        font_path, _ = get_font_and_metadata(font_name)
        font_path = font_path.as_posix()

    logger.info(f"use font: {font_path}")

    return font_path


def translate_to_word(
    files: List[str],
    output: str = "",
    lang_in: str = "en",
    lang_out: str = "zh",
    service: str = "google",
    thread: int = 0,
    model=None,
    pages: Optional[List[int]] = None,
    skip_subset_fonts: bool = True,
    keep_pdf: bool = True,
    **kwargs,
) -> str:
    """
    Translate PDF files and export as a Word document with images and tables.

    Args:
        files: list of input PDF paths
        output: output directory
        lang_in: source language
        lang_out: target language
        service: translation service (e.g. "google", "ollama:gemma2:9b")
        thread: number of threads (0=auto)
        model: layout model (OnnxModel instance)
        pages: optional page list to translate
        keep_pdf: if True, keep the intermediate mono/dual PDFs in output dir;
                  if False (default), they are deleted after the .docx is written

    Returns:
        Path to the generated .docx file
    """
    import shutil

    if not output:
        output = tempfile.mkdtemp(prefix="pdf2zh_word_")
    output_path = Path(output)
    output_path.mkdir(parents=True, exist_ok=True)

    # Intermediate PDFs go to a temp dir unless the caller wants to keep them
    pdf_dir = output_path if keep_pdf else Path(tempfile.mkdtemp(prefix="pdf2zh_pdf_"))
    elem_dir = Path(tempfile.mkdtemp(prefix="pdf2zh_elem_"))
    try:
        # Step 1: translate with element extraction
        result = translate(
            files=files,
            output=str(pdf_dir),
            lang_in=lang_in,
            lang_out=lang_out,
            service=service,
            thread=thread,
            model=model,
            pages=pages,
            extract_elements=True,
            elements_output_dir=str(elem_dir),
            skip_subset_fonts=skip_subset_fonts,
        )

        mono_pdf = result[0][0]

        # Step 2: export to Word (uses elem_dir before we clean up)
        stem = Path(mono_pdf).stem
        docx_path = str(output_path / f"{stem}.docx")
        export_pdf_to_word(mono_pdf, str(elem_dir), docx_path, lang_out=lang_out, pages=pages)
    finally:
        shutil.rmtree(str(elem_dir), ignore_errors=True)
        if not keep_pdf:
            shutil.rmtree(str(pdf_dir), ignore_errors=True)

    return docx_path


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
        shutil.rmtree(elem_dir, ignore_errors=True)

    return md_path
