#!/usr/bin/env python3
"""Create a searchable PDF with a local PaddleOCR text layer."""

from __future__ import annotations

import argparse
import importlib.metadata
import io
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Iterable


def find_paddle_root() -> Path | None:
    explicit = os.environ.get("CASE_OCR_PADDLE_ROOT")
    candidates = ([Path(explicit).expanduser()] if explicit else []) + [
        Path.home() / ".case-pdf-ocr/paddle",
        Path.home() / "Codex/tools/paddleocr",
    ]
    for root in candidates:
        if (root / "bin/python").exists():
            return root.resolve()
    return None


PADDLE_ROOT = find_paddle_root()
PADDLE_PYTHON = PADDLE_ROOT / "bin/python" if PADDLE_ROOT else None
SOURCE_CACHE = PADDLE_ROOT / "cache" if PADDLE_ROOT else None
FONT_CANDIDATES = (
    ("/System/Library/Fonts/Supplemental/Arial Unicode.ttf", 0),
    ("/System/Library/Fonts/Supplemental/Songti.ttc", 0),
    ("/System/Library/Fonts/STHeiti Light.ttc", 0),
)

np = None
pdfium = None
PdfReader = None
PdfWriter = None
pdfmetrics = None
UnicodeCIDFont = None
TTFont = None
canvas = None
FONT: str | None = None


def resolve_cache_dir(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    if SOURCE_CACHE is not None and os.access(SOURCE_CACHE.parent, os.W_OK):
        return SOURCE_CACHE.resolve()
    return (Path.home() / ".case-pdf-ocr/cache").resolve()


def maybe_reexec(cache_dir: Path) -> None:
    if os.environ.get("CASE_PDF_OCR_PADDLE_SEARCHABLE_REEXEC"):
        return
    if PADDLE_PYTHON is None or not PADDLE_PYTHON.exists() or Path(sys.prefix).resolve() == PADDLE_ROOT:
        return
    env = os.environ.copy()
    env["CASE_PDF_OCR_PADDLE_SEARCHABLE_REEXEC"] = "1"
    env["PADDLE_PDX_CACHE_HOME"] = str(cache_dir)
    env.pop("PYTHONPATH", None)
    os.execve(str(PADDLE_PYTHON), [str(PADDLE_PYTHON), __file__, *sys.argv[1:]], env)


def load_core_packages() -> list[str]:
    global np, pdfium, PdfReader, PdfWriter, pdfmetrics, UnicodeCIDFont, TTFont, canvas
    missing: list[str] = []
    try:
        import numpy as numpy_module

        np = numpy_module
    except Exception as exc:
        missing.append(f"numpy ({exc})")
    try:
        import pypdfium2 as pdfium_module

        pdfium = pdfium_module
    except Exception as exc:
        missing.append(f"pypdfium2 ({exc})")
    try:
        from pypdf import PdfReader as reader, PdfWriter as writer

        PdfReader, PdfWriter = reader, writer
    except Exception as exc:
        missing.append(f"pypdf ({exc})")
    try:
        from reportlab.pdfbase import pdfmetrics as metrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont as cid_font
        from reportlab.pdfbase.ttfonts import TTFont as tt_font
        from reportlab.pdfgen import canvas as canvas_module

        pdfmetrics, UnicodeCIDFont, TTFont, canvas = metrics, cid_font, tt_font, canvas_module
    except Exception as exc:
        missing.append(f"reportlab ({exc})")
    return missing


def register_font() -> str:
    global FONT
    if FONT:
        return FONT
    for path, index in FONT_CANDIDATES:
        if Path(path).exists():
            try:
                pdfmetrics.registerFont(TTFont("CaseOCR-CJK", path, subfontIndex=index))
                FONT = "CaseOCR-CJK"
                return FONT
            except Exception:
                continue
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    FONT = "STSong-Light"
    return FONT


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a searchable PDF with PaddleOCR.")
    parser.add_argument("pdf", nargs="?", help="source PDF")
    parser.add_argument("out", nargs="?", help="new output PDF")
    parser.add_argument("--lang", default="ch")
    parser.add_argument("--profile", choices=("fast", "balanced", "careful"), default="balanced")
    parser.add_argument("--scale", type=float)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--pages", help="1-based ranges, e.g. 1-3,5")
    selection.add_argument("--max-pages", type=int)
    parser.add_argument("--base-pdf", help="copy non-selected pages from this PDF")
    parser.add_argument("--skip-if-text", action="store_true")
    parser.add_argument("--fail-if-selected-has-text", action="store_true")
    parser.add_argument("--dump-text")
    parser.add_argument("--cache-dir")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--check-tools", action="store_true")
    args = parser.parse_args(argv)
    if args.scale is not None and args.scale <= 0:
        parser.error("--scale must be greater than 0")
    if args.max_pages is not None and args.max_pages <= 0:
        parser.error("--max-pages must be greater than 0")
    return args


def profile_scale(args: argparse.Namespace) -> float:
    return args.scale or {"fast": 1.8, "balanced": 2.2, "careful": 2.6}[args.profile]


def parse_pages(raw: str | None, total: int, max_pages: int | None) -> set[int] | None:
    if max_pages is not None:
        if max_pages <= 0:
            raise ValueError("--max-pages must be greater than 0")
        return set(range(min(max_pages, total)))
    if raw is None:
        return None
    selected: set[int] = set()
    for token in raw.split(","):
        token = token.strip()
        if not token:
            raise ValueError("empty page token")
        try:
            if "-" in token:
                start_text, end_text = token.split("-", 1)
                start, end = int(start_text), int(end_text)
            else:
                start = end = int(token)
        except ValueError as exc:
            raise ValueError(f"invalid page range: {token}") from exc
        if start < 1 or end < start or end > total:
            raise ValueError(f"page range outside 1-{total}: {token}")
        selected.update(range(start - 1, end))
    if not selected:
        raise ValueError("no pages selected")
    return selected


def ensure_cache(cache_dir: Path) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    if SOURCE_CACHE is None or not SOURCE_CACHE.exists() or cache_dir == SOURCE_CACHE.resolve():
        return
    destination = cache_dir / "official_models"
    destination.mkdir(parents=True, exist_ok=True)
    for model in ("PP-OCRv6_medium_det", "PP-OCRv6_medium_rec"):
        source = SOURCE_CACHE / "official_models" / model
        target = destination / model
        if source.exists() and not target.exists():
            shutil.copytree(source, target)


def package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def print_status(cache_dir: Path) -> bool:
    print(f"python: {sys.executable}")
    print(f"cache: {cache_dir}")
    missing = load_core_packages()
    required = ("paddlepaddle", "paddleocr", "numpy", "pypdfium2", "pypdf", "reportlab")
    for package in required:
        version = package_version(package)
        print(f"{package}: {version or 'MISSING'}")
        if version is None:
            missing.append(package)
    if not missing:
        print(f"font: {register_font()}")
    return not missing


def build_engine(lang: str, dynamic: bool = False):
    from paddleocr import PaddleOCR

    extra = {"engine": "paddle_dynamic"} if dynamic else {}
    attempts = (
        {"lang": lang, "ocr_version": "PP-OCRv6", "use_doc_orientation_classify": False, "use_doc_unwarping": False, "use_textline_orientation": False, **extra},
        {"lang": lang, "use_textline_orientation": False, **extra},
        {"lang": lang, **extra},
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
    array = np.asarray(poly, dtype=float).reshape(-1)
    if array.size == 4:
        x0, y0, x1, y1 = array
    elif array.size >= 8:
        xs, ys = array[0::2], array[1::2]
        x0, y0, x1, y1 = xs.min(), ys.min(), xs.max(), ys.max()
    else:
        return None
    if x1 <= x0 or y1 <= y0:
        return None
    return float(x0), float(y0), float(x1), float(y1)


def page_text_chars(page: object) -> int:
    try:
        return len((page.extract_text() or "").strip())
    except Exception:
        return 0


def draw_invisible(c, text: str, x_pt: float, base_pt: float, font_size: float, width_pt: float) -> None:
    font = register_font()
    text_width = pdfmetrics.stringWidth(text, font, font_size)
    horizontal_scale = min(300, max(25, width_pt / text_width * 100)) if text_width > 0 else 100
    text_object = c.beginText()
    text_object.setTextRenderMode(3)
    text_object.setFont(font, font_size)
    text_object.setTextOrigin(x_pt, base_pt)
    text_object.setHorizScale(horizontal_scale)
    text_object.textOut(text)
    c.drawText(text_object)


def add_overlay(page: object, lines: list[tuple[str, tuple[float, float, float, float]]], scale: float) -> object:
    width_pt, height_pt = float(page.mediabox.width), float(page.mediabox.height)
    buffer = io.BytesIO()
    overlay = canvas.Canvas(buffer, pagesize=(width_pt, height_pt))
    for text, (x0, y0, x1, y1) in lines:
        line_height = y1 - y0
        draw_invisible(overlay, text, x0 / scale, height_pt - (y0 + 0.82 * line_height) / scale, max(4.0, line_height / scale * 0.9), (x1 - x0) / scale)
    overlay.showPage()
    overlay.save()
    buffer.seek(0)
    page.merge_page(PdfReader(buffer).pages[0])
    return page


def atomic_write_pdf(writer, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=f".{output.stem}.", suffix=".partial.pdf", dir=output.parent, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        with temporary.open("wb") as handle:
            writer.write(handle)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", prefix=f".{path.name}.", dir=path.parent, delete=False) as handle:
        handle.write(text)
        temporary = Path(handle.name)
    temporary.replace(path)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cache_dir = resolve_cache_dir(args.cache_dir)
    os.environ["PADDLE_PDX_CACHE_HOME"] = str(cache_dir)
    maybe_reexec(cache_dir)
    if args.check_tools:
        return 0 if print_status(cache_dir) else 2
    if not args.pdf or not args.out:
        print("请提供输入 PDF 和新的输出 PDF，或使用 --check-tools。", file=sys.stderr)
        return 2

    source = Path(args.pdf).expanduser().resolve()
    output = Path(args.out).expanduser().resolve()
    base = Path(args.base_pdf).expanduser().resolve() if args.base_pdf else None
    dump = Path(args.dump_text).expanduser().resolve() if args.dump_text else None
    if not source.is_file() or source.suffix.lower() != ".pdf":
        print(f"输入 PDF 不存在：{source}", file=sys.stderr)
        return 2
    if output == source or (base and output == base):
        print("输出路径不得与输入或 base PDF 相同。", file=sys.stderr)
        return 2
    if output.exists() and not args.overwrite:
        print("输出已存在；传 --overwrite 才允许替换。", file=sys.stderr)
        return 2
    if base and not base.is_file():
        print(f"base PDF 不存在：{base}", file=sys.stderr)
        return 2
    if dump and dump in {source, output, base}:
        print("转写文本路径不得与任何 PDF 路径相同。", file=sys.stderr)
        return 2

    missing = load_core_packages()
    if missing or package_version("paddleocr") is None or package_version("paddlepaddle") is None:
        print("缺少 PaddleOCR 依赖：" + ", ".join(missing or ["paddleocr/paddlepaddle"]), file=sys.stderr)
        return 2

    reader = PdfReader(str(source))
    base_reader = PdfReader(str(base)) if base else None
    document = pdfium.PdfDocument(str(source))
    if base_reader and len(base_reader.pages) != len(reader.pages):
        print("base PDF 页数与输入不一致。", file=sys.stderr)
        return 2
    try:
        selected_pages = parse_pages(args.pages, len(reader.pages), args.max_pages)
    except ValueError as exc:
        print(f"页码参数无效：{exc}", file=sys.stderr)
        return 2
    ensure_cache(cache_dir)
    selected_indexes = selected_pages if selected_pages is not None else set(range(len(reader.pages)))
    if args.fail_if_selected_has_text:
        existing = [(index + 1, page_text_chars(page)) for index, page in enumerate(reader.pages) if index in selected_indexes and page_text_chars(page) >= 20]
        if existing:
            summary = ", ".join(f"{page}({chars}字)" for page, chars in existing[:20])
            print("选中页已有文字层，请改用无文字层原件：" + summary, file=sys.stderr)
            return 2

    engine = build_engine(args.lang)
    dynamic = False
    writer = PdfWriter()
    dump_parts: list[str] = []
    recognized_lines = 0
    attempted_pages = 0
    scale = profile_scale(args)
    for index, page in enumerate(reader.pages):
        page_number = index + 1
        if index not in selected_indexes:
            writer.add_page(base_reader.pages[index] if base_reader else page)
            dump_parts.append(f"<<<PAGE {page_number}>>>\n")
            continue
        if args.skip_if_text and page_text_chars(page) >= 20:
            writer.add_page(page)
            dump_parts.append(f"<<<PAGE {page_number}>>>\n{(page.extract_text() or '').strip()}\n")
            continue
        attempted_pages += 1
        image = np.array(document[index].render(scale=scale, grayscale=False).to_pil().convert("RGB"))
        try:
            lines = result_to_lines(engine.predict(image))
        except Exception as exc:
            if dynamic or "strides" not in str(exc):
                raise
            engine = build_engine(args.lang, dynamic=True)
            dynamic = True
            lines = result_to_lines(engine.predict(image))
        recognized_lines += len(lines)
        writer.add_page(add_overlay(page, lines, scale))
        dump_parts.append(f"<<<PAGE {page_number}>>>\n" + "\n".join(text for text, _ in lines) + "\n")
        print(f"第{page_number}页：识别{len(lines)}行", flush=True)

    if attempted_pages and recognized_lines == 0:
        print("选中页未识别出文字；未写入成果。", file=sys.stderr)
        return 1
    atomic_write_pdf(writer, output)
    if dump:
        atomic_write_text(dump, "\n".join(dump_parts))
    print(f"已保存：{output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
