#!/usr/bin/env python3
"""Assess PDF pages and recommend OCRmyPDF or PaddleOCR per page."""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from pathlib import Path
from statistics import mean


# 依赖解释器探测顺序：环境变量 CASE_OCR_PYTHON > 标准安装位置 > Codex 捆绑运行时 > 当前解释器
PYTHON_CANDIDATES = (
    Path.home() / ".case-pdf-ocr/venv/bin/python3",
    Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3",
)


def adapt_runtime() -> None:
    if os.environ.get("CASE_PDF_OCR_ASSESS_REEXEC"):
        return
    explicit = os.environ.get("CASE_OCR_PYTHON")
    candidates = ([Path(explicit).expanduser()] if explicit else []) + list(PYTHON_CANDIDATES)
    for python in candidates:
        if python.exists() and Path(sys.executable).resolve() != python.resolve():
            env = os.environ.copy()
            env["CASE_PDF_OCR_ASSESS_REEXEC"] = "1"
            env.pop("PYTHONPATH", None)
            os.execve(str(python), [str(python), __file__, *sys.argv[1:]], env)


adapt_runtime()

try:
    import numpy as np  # noqa: E402
    import pypdfium2 as pdfium  # noqa: E402
    from pypdf import PdfReader  # noqa: E402
except ImportError as exc:
    raise SystemExit(
        f"缺少 Python 依赖：{exc.name}。请按 INSTALL.md 创建环境：\n"
        "  python3 -m venv ~/.case-pdf-ocr/venv\n"
        "  ~/.case-pdf-ocr/venv/bin/pip install numpy pypdf pypdfium2 pillow reportlab\n"
        "或设置环境变量 CASE_OCR_PYTHON 指向已装齐依赖的 Python。"
    )


FIELDS = [
    "pdf",
    "page",
    "pages",
    "decision",
    "reason",
    "text_chars",
    "width",
    "height",
    "rotation",
    "dark_density",
    "line_bands",
    "column_bands",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Assess OCR route per PDF page.")
    parser.add_argument("paths", nargs="+", help="PDF files or folders")
    parser.add_argument("--output-dir", help="assessment output directory")
    parser.add_argument("--no-recursive", action="store_true")
    parser.add_argument("--max-files", type=int)
    parser.add_argument("--max-pages", type=int)
    parser.add_argument("--render-scale", type=float, default=0.45)
    parser.add_argument("--min-text-chars", type=int, default=20)
    parser.add_argument("--dense-line-threshold", type=int, default=55)
    parser.add_argument("--dense-column-threshold", type=int, default=45)
    parser.add_argument("--dark-density-threshold", type=float, default=0.07)
    return parser.parse_args()


def find_pdfs(paths: list[str], recursive: bool) -> list[Path]:
    pdfs: list[Path] = []
    for raw in paths:
        path = Path(raw).expanduser().resolve()
        if path.is_file() and path.suffix.lower() == ".pdf":
            pdfs.append(path)
        elif path.is_dir():
            iterator = path.rglob("*.pdf") if recursive else path.glob("*.pdf")
            pdfs.extend(p.resolve() for p in iterator if p.is_file())
    return sorted(dict.fromkeys(pdfs))


def is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def common_root(paths: list[str], pdfs: list[Path]) -> Path:
    roots: list[str] = []
    for raw in paths:
        path = Path(raw).expanduser().resolve()
        roots.append(str(path if path.is_dir() else path.parent))
    if not roots and pdfs:
        roots.append(str(pdfs[0].parent))
    return Path(os.path.commonpath(roots)).resolve()


def safe_name(pdf: Path) -> str:
    return re.sub(r"[\\/:*?\"<>|\s]+", "_", pdf.stem).strip("_") or "pdf"


def page_text_chars(page: object) -> int:
    try:
        return len((page.extract_text() or "").strip())
    except Exception:
        return 0


def count_bands(values: np.ndarray) -> int:
    bands = 0
    in_band = False
    for value in values:
        if value and not in_band:
            bands += 1
            in_band = True
        elif not value:
            in_band = False
    return bands


def render_features(doc: pdfium.PdfDocument, index: int, scale: float) -> tuple[float, int, int]:
    image = doc[index].render(scale=scale, grayscale=True).to_pil()
    arr = np.asarray(image, dtype=np.uint8)
    dark = arr < 190
    density = float(dark.mean())
    row_has_ink = dark.mean(axis=1) > 0.015
    column_has_ink = dark.mean(axis=0) > 0.015
    return density, count_bands(row_has_ink), count_bands(column_has_ink)


def decide(
    text_chars: int,
    width: float,
    height: float,
    rotation: int,
    density: float,
    bands: int,
    column_bands: int,
    args: argparse.Namespace,
) -> tuple[str, str]:
    if text_chars >= args.min_text_chars:
        return "skip-text", "已有文字层，交给 OCRmyPDF skip-text 保留"
    landscape = width > height * 1.08 or rotation in {90, 270}
    if landscape:
        return "paddle", "横向/旋转页，PaddleOCR 更适合按行定位"
    if bands >= args.dense_line_threshold:
        return "paddle", "文字行/表格线密集，PaddleOCR 更适合"
    if column_bands >= args.dense_column_threshold:
        return "paddle", "列结构/表格线密集，PaddleOCR 更适合"
    if density >= args.dark_density_threshold:
        return "paddle", "页面墨迹密度高，疑似表格/复杂扫描"
    return "ocrmypdf", "普通扫描页，优先 OCRmyPDF/Tesseract"


def range_string(pages: list[int]) -> str:
    if not pages:
        return ""
    pages = sorted(set(pages))
    ranges: list[str] = []
    start = prev = pages[0]
    for page in pages[1:]:
        if page == prev + 1:
            prev = page
            continue
        ranges.append(f"{start}" if start == prev else f"{start}-{prev}")
        start = prev = page
    ranges.append(f"{start}" if start == prev else f"{start}-{prev}")
    return ",".join(ranges)


def assess_pdf(pdf: Path, args: argparse.Namespace) -> list[dict[str, str]]:
    reader = PdfReader(str(pdf))
    doc = pdfium.PdfDocument(str(pdf))
    total = len(reader.pages)
    limit = min(total, args.max_pages or total)
    rows: list[dict[str, str]] = []
    for index in range(limit):
        page = reader.pages[index]
        text_chars = page_text_chars(page)
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        rotation = int(getattr(page, "rotation", 0) or 0)
        density = 0.0
        bands = 0
        column_bands = 0
        if text_chars < args.min_text_chars:
            try:
                density, bands, column_bands = render_features(doc, index, args.render_scale)
            except Exception:
                density, bands, column_bands = 0.0, 0, 0
        decision, reason = decide(text_chars, width, height, rotation, density, bands, column_bands, args)
        rows.append(
            {
                "pdf": str(pdf),
                "page": str(index + 1),
                "pages": str(total),
                "decision": decision,
                "reason": reason,
                "text_chars": str(text_chars),
                "width": f"{width:.1f}",
                "height": f"{height:.1f}",
                "rotation": str(rotation),
                "dark_density": f"{density:.4f}",
                "line_bands": str(bands),
                "column_bands": str(column_bands),
            }
        )
    return rows


def write_report(report_dir: Path, rows: list[dict[str, str]]) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    csv_path = report_dir / "ocr_strategy.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    by_pdf: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_pdf.setdefault(row["pdf"], []).append(row)

    lines = ["# OCR 分流评估", ""]
    for pdf, pdf_rows in by_pdf.items():
        paddle_pages = [int(r["page"]) for r in pdf_rows if r["decision"] == "paddle"]
        ocrmypdf_pages = [int(r["page"]) for r in pdf_rows if r["decision"] in {"ocrmypdf", "skip-text"}]
        densities = [float(r["dark_density"]) for r in pdf_rows if r["dark_density"]]
        bands = [int(r["line_bands"]) for r in pdf_rows if r["line_bands"]]
        column_bands = [int(r["column_bands"]) for r in pdf_rows if r["column_bands"]]
        name = safe_name(Path(pdf))
        (report_dir / f"{name}.paddle_pages.txt").write_text(range_string(paddle_pages) + "\n", encoding="utf-8")
        (report_dir / f"{name}.ocrmypdf_pages.txt").write_text(range_string(ocrmypdf_pages) + "\n", encoding="utf-8")
        lines.extend(
            [
                f"## {pdf}",
                "",
                f"- 评估页数：{len(pdf_rows)} / {pdf_rows[0]['pages'] if pdf_rows else 0}",
                f"- OCRmyPDF/保留文字层页：{range_string(ocrmypdf_pages) or '无'}",
                f"- PaddleOCR 建议页：{range_string(paddle_pages) or '无'}",
                f"- 平均墨迹密度：{mean(densities):.4f}" if densities else "- 平均墨迹密度：无",
                f"- 平均行带数：{mean(bands):.1f}" if bands else "- 平均行带数：无",
                f"- 平均列带数：{mean(column_bands):.1f}" if column_bands else "- 平均列带数：无",
                "",
                "建议：先并行跑 OCRmyPDF 基础版和 PaddleOCR 建议页；基础版完成后，如需混合成品，再用 `paddle_searchable_pdf.py --base-pdf` 输出最终增强版。",
                "",
            ]
        )
    (report_dir / "ocr_strategy.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    pdfs = find_pdfs(args.paths, recursive=not args.no_recursive)
    if args.max_files:
        pdfs = pdfs[: args.max_files]
    if not pdfs:
        print("No PDF files found.", file=sys.stderr)
        return 2
    root = common_root(args.paths, pdfs)
    excluded_roots = (root / "OCR成果", root / "OCR过程文件")
    pdfs = [p for p in pdfs if not any(is_under(p, excluded) for excluded in excluded_roots)]
    report_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else root / "OCR过程文件" / "报告"
    rows: list[dict[str, str]] = []
    for pdf in pdfs:
        print(f"评估 {pdf}", flush=True)
        rows.extend(assess_pdf(pdf, args))
    write_report(report_dir, rows)
    print(f"Strategy CSV: {report_dir / 'ocr_strategy.csv'}")
    print(f"Strategy report: {report_dir / 'ocr_strategy.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
