#!/usr/bin/env python3
"""Use PaddleOCR to create a searchable PDF for difficult Chinese legal scans."""

from __future__ import annotations

import argparse
import importlib.util
import io
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Iterable


PADDLE_TOOL_ROOT = Path("/Users/xuqianchuan/Documents/Codex/tools/paddleocr")
PADDLE_PYTHON = PADDLE_TOOL_ROOT / "bin/python"
SOURCE_CACHE = PADDLE_TOOL_ROOT / "cache"
BUNDLED_SITE_PACKAGES = Path(
    "/Users/xuqianchuan/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/site-packages"
)
DEFAULT_CACHE_DIR = Path.cwd() / "OCR过程文件" / "PaddleOCR缓存"
FONT = "STSong-Light"


def load_bundled_package(name: str) -> None:
    if name in sys.modules:
        return
    init_file = BUNDLED_SITE_PACKAGES / name / "__init__.py"
    if not init_file.exists():
        return
    spec = importlib.util.spec_from_file_location(
        name,
        init_file,
        submodule_search_locations=[str(init_file.parent)],
    )
    if spec is None or spec.loader is None:
        return
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)


def preparse_cache_dir(argv: list[str]) -> Path:
    for idx, arg in enumerate(argv):
        if arg == "--cache-dir" and idx + 1 < len(argv):
            return Path(argv[idx + 1]).expanduser().resolve()
        if arg.startswith("--cache-dir="):
            return Path(arg.split("=", 1)[1]).expanduser().resolve()
    return DEFAULT_CACHE_DIR.resolve()


def adapt_runtime() -> None:
    cache_dir = preparse_cache_dir(sys.argv[1:])
    os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(cache_dir))
    if (
        not os.environ.get("CASE_PDF_OCR_PADDLE_SEARCHABLE_REEXEC")
        and PADDLE_PYTHON.exists()
        and Path(sys.executable).resolve() != PADDLE_PYTHON.resolve()
    ):
        env = os.environ.copy()
        env["CASE_PDF_OCR_PADDLE_SEARCHABLE_REEXEC"] = "1"
        env.pop("PYTHONPATH", None)
        os.execve(str(PADDLE_PYTHON), [str(PADDLE_PYTHON), __file__, *sys.argv[1:]], env)
    load_bundled_package("pypdf")
    load_bundled_package("reportlab")


adapt_runtime()

import numpy as np  # noqa: E402
import pypdfium2 as pdfium  # noqa: E402
from pypdf import PdfReader, PdfWriter  # noqa: E402
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.cidfonts import UnicodeCIDFont  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402


pdfmetrics.registerFont(UnicodeCIDFont(FONT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a searchable PDF with PaddleOCR invisible text overlay.",
    )
    parser.add_argument("pdf", nargs="?", help="source PDF")
    parser.add_argument("out", nargs="?", help="output searchable PDF")
    parser.add_argument("--lang", default="ch", help="PaddleOCR language, e.g. ch, chinese_cht")
    parser.add_argument(
        "--profile",
        choices=("fast", "balanced", "careful"),
        default="balanced",
        help="fast uses lower render scale; careful uses higher scale for small or poor scans",
    )
    parser.add_argument("--scale", type=float, help="render scale override")
    parser.add_argument("--pages", help="1-based page ranges, e.g. 1-3,5,9-10")
    parser.add_argument("--max-pages", type=int, help="process only the first N pages")
    parser.add_argument("--base-pdf", help="optional OCRmyPDF base PDF; non-selected pages are copied from it")
    parser.add_argument("--skip-if-text", action="store_true", help="preserve pages with an existing text layer")
    parser.add_argument(
        "--fail-if-selected-has-text",
        action="store_true",
        help="abort if pages selected for PaddleOCR already contain a text layer; use an image-only source PDF instead",
    )
    parser.add_argument("--dump-text", help="write recognized text with <<<PAGE N>>> markers")
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR), help="writable PaddleOCR cache directory")
    parser.add_argument("--check-tools", action="store_true", help="print dependency status and exit")
    return parser.parse_args()


def profile_scale(args: argparse.Namespace) -> float:
    if args.scale:
        return args.scale
    return {"fast": 1.8, "balanced": 2.2, "careful": 2.6}[args.profile]


def parse_pages(raw: str | None, total: int, max_pages: int | None) -> set[int] | None:
    if max_pages is not None:
        return set(range(min(max_pages, total)))
    if not raw:
        return None
    selected: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            start, end = int(start_s), int(end_s)
            selected.update(range(start - 1, end))
        else:
            selected.add(int(part) - 1)
    return {idx for idx in selected if 0 <= idx < total}


def ensure_cache(cache_dir: Path) -> None:
    (cache_dir / "official_models").mkdir(parents=True, exist_ok=True)
    source_models = SOURCE_CACHE / "official_models"
    for model in ("PP-OCRv6_medium_det", "PP-OCRv6_medium_rec"):
        src = source_models / model
        dst = cache_dir / "official_models" / model
        if src.exists() and not dst.exists():
            shutil.copytree(src, dst)


def build_engine(lang: str):
    from paddleocr import PaddleOCR

    attempts = (
        {
            "lang": lang,
            "ocr_version": "PP-OCRv6",
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_textline_orientation": False,
        },
        {"lang": lang, "use_textline_orientation": False},
        {"lang": lang},
    )
    last_error: Exception | None = None
    for kwargs in attempts:
        try:
            return PaddleOCR(**kwargs)
        except (TypeError, ValueError) as exc:
            last_error = exc
    if last_error:
        raise last_error
    return PaddleOCR(lang=lang)


def result_to_lines(result: Iterable[object]) -> list[tuple[str, tuple[float, float, float, float]]]:
    lines: list[tuple[str, tuple[float, float, float, float]]] = []
    for page in result:
        data = page if isinstance(page, dict) else getattr(page, "json", page)
        if isinstance(data, dict) and isinstance(data.get("res"), dict):
            data = data["res"]
        if not isinstance(data, dict):
            continue
        texts = data.get("rec_texts") or data.get("rec_text") or []
        boxes = data.get("rec_boxes")
        if boxes is None or len(boxes) == 0:
            boxes = data.get("dt_polys") or data.get("rec_polys") or []
        for text, box in zip(texts, boxes):
            normalized = poly_to_box(box)
            if text and normalized:
                lines.append((str(text), normalized))
    return lines


def poly_to_box(poly: object) -> tuple[float, float, float, float] | None:
    arr = np.asarray(poly, dtype=float).reshape(-1)
    if arr.size == 4:
        x0, y0, x1, y1 = arr
    elif arr.size >= 8:
        xs = arr[0::2]
        ys = arr[1::2]
        x0, y0, x1, y1 = xs.min(), ys.min(), xs.max(), ys.max()
    else:
        return None
    if x1 <= x0 or y1 <= y0:
        return None
    return float(x0), float(y0), float(x1), float(y1)


def page_has_text(page: object) -> bool:
    return page_text_chars(page) >= 20


def page_text_chars(page: object) -> int:
    try:
        return len((page.extract_text() or "").strip())
    except Exception:
        return 0


def draw_invisible(c: canvas.Canvas, text: str, x_pt: float, base_pt: float, fs: float, width_pt: float) -> None:
    text_width = pdfmetrics.stringWidth(text, FONT, fs)
    horiz_scale = min(300, max(25, width_pt / text_width * 100)) if text_width > 0 else 100
    text_obj = c.beginText()
    text_obj.setTextRenderMode(3)
    text_obj.setFont(FONT, fs)
    text_obj.setTextOrigin(x_pt, base_pt)
    text_obj.setHorizScale(horiz_scale)
    text_obj.textOut(text)
    c.drawText(text_obj)


def add_overlay(page: object, lines: list[tuple[str, tuple[float, float, float, float]]], scale: float) -> object:
    width_pt = float(page.mediabox.width)
    height_pt = float(page.mediabox.height)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(width_pt, height_pt))
    for text, (x0, y0, x1, y1) in lines:
        line_height = y1 - y0
        font_size = max(4.0, line_height / scale * 0.9)
        baseline = height_pt - (y0 + 0.82 * line_height) / scale
        draw_invisible(c, text, x0 / scale, baseline, font_size, (x1 - x0) / scale)
    c.showPage()
    c.save()
    buf.seek(0)
    page.merge_page(PdfReader(buf).pages[0])
    return page


def print_status(args: argparse.Namespace) -> None:
    print(f"python: {sys.executable}")
    print(f"cache: {Path(args.cache_dir).expanduser().resolve()}")
    for package in ("paddleocr", "paddle", "pypdfium2", "pypdf", "reportlab", "numpy"):
        try:
            module = __import__(package)
            print(f"{package}: {getattr(module, '__version__', 'ok')}")
        except Exception as exc:
            print(f"{package}: MISSING ({exc})")


def main() -> int:
    args = parse_args()
    if args.check_tools:
        print_status(args)
        return 0
    if not args.pdf or not args.out:
        print("Provide input and output PDFs, or use --check-tools.", file=sys.stderr)
        return 2

    cache_dir = Path(args.cache_dir).expanduser().resolve()
    os.environ["PADDLE_PDX_CACHE_HOME"] = str(cache_dir)
    ensure_cache(cache_dir)

    source = Path(args.pdf).expanduser().resolve()
    output = Path(args.out).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    dump = Path(args.dump_text).expanduser().resolve() if args.dump_text else None
    if dump:
        dump.parent.mkdir(parents=True, exist_ok=True)

    scale = profile_scale(args)
    reader = PdfReader(str(source))
    base_reader = PdfReader(str(Path(args.base_pdf).expanduser().resolve())) if args.base_pdf else None
    doc = pdfium.PdfDocument(str(source))
    if base_reader and len(base_reader.pages) != len(reader.pages):
        print("base PDF page count does not match source PDF", file=sys.stderr)
        return 2
    selected_pages = parse_pages(args.pages, len(reader.pages), args.max_pages)
    if args.fail_if_selected_has_text:
        selected_indexes = selected_pages if selected_pages is not None else set(range(len(reader.pages)))
        existing_text_pages = [
            (index + 1, chars)
            for index, page in enumerate(reader.pages)
            if index in selected_indexes and (chars := page_text_chars(page)) >= 20
        ]
        if existing_text_pages:
            summary = ", ".join(f"{page_no}({chars})" for page_no, chars in existing_text_pages[:20])
            print(
                "selected pages already contain text layer; rebuild from image-only source PDF first: " + summary,
                file=sys.stderr,
            )
            return 2
    engine = build_engine(args.lang)
    writer = PdfWriter()

    dump_handle = dump.open("w", encoding="utf-8") if dump else None
    try:
        for index, page in enumerate(reader.pages):
            page_no = index + 1
            if selected_pages is not None and index not in selected_pages:
                writer.add_page(base_reader.pages[index] if base_reader else page)
                if dump_handle:
                    dump_handle.write(f"<<<PAGE {page_no}>>>\n\n")
                continue
            if args.skip_if_text and page_has_text(page):
                writer.add_page(page)
                text = (page.extract_text() or "").strip()
                if dump_handle:
                    dump_handle.write(f"<<<PAGE {page_no}>>>\n{text}\n")
                print(f"第{page_no}页: 已有文字层，跳过", flush=True)
                continue
            existing_chars = page_text_chars(page)
            if existing_chars >= 20:
                print(f"第{page_no}页: 警告，输入页已有{existing_chars}字文字层，将叠加新文字层", flush=True)

            image = np.array(doc[index].render(scale=scale, grayscale=False).to_pil().convert("RGB"))
            lines = result_to_lines(engine.predict(image))
            writer.add_page(add_overlay(page, lines, scale))
            if dump_handle:
                dump_handle.write(f"<<<PAGE {page_no}>>>\n" + "\n".join(text for text, _ in lines) + "\n")
            print(f"第{page_no}页: 识别{len(lines)}行", flush=True)
    finally:
        if dump_handle:
            dump_handle.close()

    with output.open("wb") as handle:
        writer.write(handle)
    print(f"已保存 {output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
