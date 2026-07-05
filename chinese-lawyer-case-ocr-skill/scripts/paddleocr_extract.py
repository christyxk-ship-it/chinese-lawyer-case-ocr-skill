#!/usr/bin/env python3
"""Extract OCR text and structure from case PDFs/images with PaddleOCR.

This is an enhancement route for difficult Chinese legal materials. It writes
sidecar text and JSON/coordinate results, but it does not create searchable PDFs.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path
from typing import Iterable, Any


DEFAULT_TOOL_ROOT = Path("/Users/xuqianchuan/Documents/Codex/tools/paddleocr")
DEFAULT_PADDLEOCR_PYTHON = DEFAULT_TOOL_ROOT / "bin/python"
DEFAULT_CACHE_DIR = DEFAULT_TOOL_ROOT / "cache"

INPUT_SUFFIXES = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
    ".bmp",
    ".webp",
}

MANIFEST_FIELDS = [
    "source",
    "status",
    "results",
    "text_chars",
    "json",
    "text",
    "log",
    "seconds",
    "note",
]


def preparse_cache_dir(argv: list[str]) -> Path:
    for index, arg in enumerate(argv):
        if arg == "--cache-dir" and index + 1 < len(argv):
            return Path(argv[index + 1]).expanduser().resolve()
        if arg.startswith("--cache-dir="):
            return Path(arg.split("=", 1)[1]).expanduser().resolve()
    return DEFAULT_CACHE_DIR


def maybe_reexec_with_paddle_python() -> None:
    if os.environ.get("CASE_PDF_OCR_PADDLE_REEXEC"):
        return
    if not DEFAULT_PADDLEOCR_PYTHON.exists():
        return
    if Path(sys.prefix).resolve() == DEFAULT_TOOL_ROOT.resolve():
        return
    env = os.environ.copy()
    env["CASE_PDF_OCR_PADDLE_REEXEC"] = "1"
    env.setdefault("PADDLE_PDX_CACHE_HOME", str(preparse_cache_dir(sys.argv[1:])))
    os.execve(str(DEFAULT_PADDLEOCR_PYTHON), [str(DEFAULT_PADDLEOCR_PYTHON), __file__, *sys.argv[1:]], env)


os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(preparse_cache_dir(sys.argv[1:])))
maybe_reexec_with_paddle_python()


def load_paddleocr():
    try:
        from paddleocr import PaddleOCR

        return PaddleOCR
    except Exception as exc:
        raise SystemExit(
            "PaddleOCR is not importable. Install it in "
            f"{DEFAULT_TOOL_ROOT} or run this script with a Python environment "
            f"that has paddleocr installed. Original error: {exc}"
        )


def json_default(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return value.tolist()
    if hasattr(value, "item"):
        return value.item()
    return str(value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract OCR text/JSON with PaddleOCR for difficult case materials.",
    )
    parser.add_argument("paths", nargs="*", help="PDF/image files or folders to process")
    parser.add_argument("--lang", default="ch", help="PaddleOCR language, e.g. ch, chinese_cht, en")
    parser.add_argument(
        "--ocr-version",
        default="PP-OCRv6",
        choices=("PP-OCRv3", "PP-OCRv4", "PP-OCRv5", "PP-OCRv6"),
        help="PaddleOCR model family",
    )
    parser.add_argument("--output-dir", help="Directory for text sidecars")
    parser.add_argument("--json-dir", help="Directory for PaddleOCR JSON results")
    parser.add_argument("--report-dir", help="Directory for manifest and QA report")
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR), help="PaddleX/PaddleOCR cache directory")
    parser.add_argument("--max-files", type=int, help="Process only the first N files")
    parser.add_argument("--no-recursive", action="store_true", help="Do not recurse folders")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing outputs")
    parser.add_argument("--no-resume", action="store_true", help="Do not skip prior ok rows")
    parser.add_argument("--use-doc-orientation-classify", action="store_true", help="Enable document orientation classification")
    parser.add_argument("--use-doc-unwarping", action="store_true", help="Enable document unwarping")
    parser.add_argument("--use-textline-orientation", action="store_true", help="Enable textline orientation classification")
    parser.add_argument("--return-word-box", action="store_true", help="Return word boxes when supported")
    parser.add_argument("--text-rec-score-thresh", type=float, help="Drop recognition results below this score")
    parser.add_argument("--check-tools", action="store_true", help="Print PaddleOCR dependency status and exit")
    return parser.parse_args()


def find_inputs(paths: Iterable[str], recursive: bool) -> list[Path]:
    files: list[Path] = []
    for raw in paths:
        path = Path(raw).expanduser().resolve()
        if path.is_file() and path.suffix.lower() in INPUT_SUFFIXES:
            files.append(path)
        elif path.is_dir():
            iterator = path.rglob("*") if recursive else path.glob("*")
            files.extend(p.resolve() for p in iterator if p.is_file() and p.suffix.lower() in INPUT_SUFFIXES)
    return sorted(dict.fromkeys(files))


def common_root(paths: list[str], files: list[Path]) -> Path:
    roots: list[str] = []
    for raw in paths:
        path = Path(raw).expanduser().resolve()
        roots.append(str(path if path.is_dir() else path.parent))
    if not roots and files:
        roots = [str(files[0].parent)]
    if not roots:
        return Path.cwd().resolve()
    return Path(os.path.commonpath(roots)).resolve()


def default_dirs(root: Path, args: argparse.Namespace) -> tuple[Path, Path, Path]:
    text_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else root / "PaddleOCR文本"
    json_dir = Path(args.json_dir).expanduser().resolve() if args.json_dir else root / "PaddleOCR结构"
    report_dir = Path(args.report_dir).expanduser().resolve() if args.report_dir else root / "PaddleOCR报告"
    return text_dir, json_dir, report_dir


def should_exclude(path: Path, text_dir: Path, json_dir: Path, report_dir: Path) -> bool:
    for root in (text_dir.resolve(), json_dir.resolve(), report_dir.resolve()):
        try:
            path.relative_to(root)
            return True
        except ValueError:
            pass
    return path.name.endswith("_OCR.pdf")


def sidecar_paths(src: Path, root: Path, text_dir: Path, json_dir: Path) -> tuple[Path, Path]:
    try:
        rel = src.relative_to(root)
    except ValueError:
        rel = Path(src.name)
    txt = (text_dir / rel).with_suffix(".txt")
    js = (json_dir / rel).with_suffix(".json")
    return txt, js


def read_manifest(report_dir: Path) -> dict[str, dict[str, str]]:
    path = report_dir / "paddleocr_manifest.csv"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8-sig") as handle:
        return {row["source"]: row for row in csv.DictReader(handle)}


def write_manifest(report_dir: Path, rows: list[dict[str, str]]) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    with (report_dir / "paddleocr_manifest.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    failures = [row for row in rows if row["status"] != "ok"]
    failed_path = report_dir / "failed_paddleocr_files.txt"
    if failures:
        with failed_path.open("w", encoding="utf-8") as handle:
            for row in failures:
                handle.write(f"{row['status']}\t{row['source']}\t{row['note']}\n")
    elif failed_path.exists():
        failed_path.unlink()


def result_to_json(result: Any) -> Any:
    if hasattr(result, "json"):
        return result.json
    if isinstance(result, dict):
        return result
    return {"raw": result}


def extract_texts(result_jsons: list[Any]) -> list[str]:
    parts: list[str] = []
    for fallback_index, item in enumerate(result_jsons, start=1):
        res = item.get("res", item) if isinstance(item, dict) else {}
        page_index = res.get("page_index")
        if page_index is None:
            page_label = str(fallback_index)
        else:
            page_label = str(int(page_index) + 1)
        texts = res.get("rec_texts") or []
        if texts:
            parts.append(f"===== Result {page_label} =====")
            parts.extend(str(text) for text in texts)
    return parts


def write_quality_report(report_dir: Path, rows: list[dict[str, str]]) -> None:
    status_counts: dict[str, int] = {}
    for row in rows:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
    low_text = [
        row
        for row in rows
        if row["status"] == "ok" and row.get("text_chars", "0").isdigit() and int(row["text_chars"]) < 20
    ]
    failures = [row for row in rows if row["status"] != "ok"]
    lines = [
        "# PaddleOCR质量检查",
        "",
        f"- 清单文件数：{len(rows)}",
        "- 状态统计：" + ", ".join(f"{key}={value}" for key, value in sorted(status_counts.items())),
        f"- 低文本输出：{len(low_text)}",
        f"- 失败：{len(failures)}",
        "- 说明：PaddleOCR增强路线只生成文本和JSON结构，不生成可检索PDF。",
    ]
    if failures:
        lines.extend(["", "## 失败清单", ""])
        lines.extend(f"- {row['status']}: {row['source']} {row['note']}".rstrip() for row in failures[:100])
    if low_text:
        lines.extend(["", "## 低文本清单", ""])
        lines.extend(f"- {row['source']}" for row in low_text[:100])
    (report_dir / "PaddleOCR质量检查.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_ocr(args: argparse.Namespace):
    PaddleOCR = load_paddleocr()
    return PaddleOCR(
        lang=args.lang,
        ocr_version=args.ocr_version,
        use_doc_orientation_classify=args.use_doc_orientation_classify,
        use_doc_unwarping=args.use_doc_unwarping,
        use_textline_orientation=args.use_textline_orientation,
        text_rec_score_thresh=args.text_rec_score_thresh,
        return_word_box=args.return_word_box,
    )


def print_tool_status(args: argparse.Namespace) -> None:
    print(f"python: {sys.executable}")
    print(f"cache: {os.environ.get('PADDLE_PDX_CACHE_HOME')}")
    try:
        import paddle
        import paddleocr

        print(f"paddle: {paddle.__version__}")
        print(f"paddleocr: {getattr(paddleocr, '__version__', 'unknown')}")
    except Exception as exc:
        print(f"paddleocr import: failed ({exc})")


def main() -> int:
    args = parse_args()
    os.environ["PADDLE_PDX_CACHE_HOME"] = str(Path(args.cache_dir).expanduser().resolve())
    if args.check_tools:
        print_tool_status(args)
        return 0
    if not args.paths:
        print("Provide at least one PDF/image file or folder, or use --check-tools.", file=sys.stderr)
        return 2

    files = find_inputs(args.paths, recursive=not args.no_recursive)
    if args.max_files:
        files = files[: args.max_files]
    root = common_root(args.paths, files)
    text_dir, json_dir, report_dir = default_dirs(root, args)
    files = [p for p in files if not should_exclude(p, text_dir, json_dir, report_dir)]

    existing_rows = read_manifest(report_dir) if not args.no_resume else {}
    rows: list[dict[str, str]] = []
    ocr = None
    for index, src in enumerate(files, start=1):
        txt_path, json_path = sidecar_paths(src, root, text_dir, json_dir)
        existing = existing_rows.get(str(src))
        if (
            existing
            and not args.overwrite
            and existing.get("status") == "ok"
            and Path(existing.get("json") or json_path).exists()
            and Path(existing.get("text") or txt_path).exists()
        ):
            rows.append(existing)
            print(f"[{index}/{len(files)}] resume {src}")
            write_manifest(report_dir, rows)
            continue

        if ocr is None:
            ocr = build_ocr(args)

        print(f"[{index}/{len(files)}] {src}")
        txt_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        start = time.monotonic()
        row = {
            "source": str(src),
            "status": "ok",
            "results": "0",
            "text_chars": "0",
            "json": str(json_path),
            "text": str(txt_path),
            "log": "",
            "seconds": "0.0",
            "note": "",
        }
        try:
            results = ocr.predict(str(src))
            result_jsons = [result_to_json(result) for result in results]
            texts = extract_texts(result_jsons)
            text = "\n".join(texts).strip() + ("\n" if texts else "")
            json_path.write_text(json.dumps(result_jsons, ensure_ascii=False, indent=2, default=json_default) + "\n", encoding="utf-8")
            txt_path.write_text(text, encoding="utf-8")
            row["results"] = str(len(result_jsons))
            row["text_chars"] = str(len(text.strip()))
            if len(text.strip()) < 20:
                row["note"] = "low extracted text; spot-check visually"
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            row["status"] = "failed"
            row["note"] = str(exc)
        finally:
            row["seconds"] = f"{time.monotonic() - start:.1f}"
        rows.append(row)
        write_manifest(report_dir, rows)

    write_manifest(report_dir, rows)
    write_quality_report(report_dir, rows)
    print(f"Files scanned: {len(files)}")
    print(f"Manifest: {report_dir / 'paddleocr_manifest.csv'}")
    print(f"Quality report: {report_dir / 'PaddleOCR质量检查.md'}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
