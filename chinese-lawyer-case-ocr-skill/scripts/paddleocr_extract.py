#!/usr/bin/env python3
"""Extract local PaddleOCR text and JSON sidecars into OCR成果."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable


INPUT_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


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


def resolve_cache_dir(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    if SOURCE_CACHE is not None and os.access(SOURCE_CACHE.parent, os.W_OK):
        return SOURCE_CACHE.resolve()
    return (Path.home() / ".case-pdf-ocr/cache").resolve()


def maybe_reexec(cache_dir: Path) -> None:
    if os.environ.get("CASE_PDF_OCR_PADDLE_REEXEC"):
        return
    if PADDLE_PYTHON is None or not PADDLE_PYTHON.exists() or Path(sys.prefix).resolve() == PADDLE_ROOT:
        return
    env = os.environ.copy()
    env["CASE_PDF_OCR_PADDLE_REEXEC"] = "1"
    env["PADDLE_PDX_CACHE_HOME"] = str(cache_dir)
    env.pop("PYTHONPATH", None)
    os.execve(str(PADDLE_PYTHON), [str(PADDLE_PYTHON), __file__, *sys.argv[1:]], env)


def package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract PaddleOCR text and JSON into OCR成果.")
    parser.add_argument("paths", nargs="*")
    parser.add_argument("--lang", default="ch")
    parser.add_argument("--ocr-version", default="PP-OCRv6", choices=("PP-OCRv3", "PP-OCRv4", "PP-OCRv5", "PP-OCRv6"))
    parser.add_argument("--output-dir", help="default: <input root>/OCR成果")
    parser.add_argument("--cache-dir")
    parser.add_argument("--max-files", type=int)
    parser.add_argument("--no-recursive", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--use-doc-orientation-classify", action="store_true")
    parser.add_argument("--use-doc-unwarping", action="store_true")
    parser.add_argument("--use-textline-orientation", action="store_true")
    parser.add_argument("--return-word-box", action="store_true")
    parser.add_argument("--text-rec-score-thresh", type=float)
    parser.add_argument("--check-tools", action="store_true")
    args = parser.parse_args(argv)
    if args.max_files is not None and args.max_files <= 0:
        parser.error("--max-files must be greater than 0")
    if args.text_rec_score_thresh is not None and not 0 <= args.text_rec_score_thresh <= 1:
        parser.error("--text-rec-score-thresh must be between 0 and 1")
    return args


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


def common_root(paths: list[str]) -> Path:
    roots = []
    for raw in paths:
        path = Path(raw).expanduser().resolve()
        roots.append(str(path if path.is_dir() else path.parent))
    return Path(os.path.commonpath(roots)).resolve()


def is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def output_paths(source: Path, root: Path, output_dir: Path) -> tuple[Path, Path]:
    try:
        relative = source.relative_to(root)
    except ValueError:
        relative = Path(source.name)
    base = output_dir / relative
    return base.with_name(f"{base.stem}_Paddle.txt"), base.with_name(f"{base.stem}_Paddle.json")


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


def print_status(cache_dir: Path) -> bool:
    print(f"python: {sys.executable}")
    print(f"cache: {cache_dir}")
    versions = {name: package_version(name) for name in ("paddlepaddle", "paddleocr")}
    for name, version in versions.items():
        print(f"{name}: {version or 'MISSING'}")
    return all(versions.values())


def build_ocr(args: argparse.Namespace):
    from paddleocr import PaddleOCR

    return PaddleOCR(
        lang=args.lang,
        ocr_version=args.ocr_version,
        use_doc_orientation_classify=args.use_doc_orientation_classify,
        use_doc_unwarping=args.use_doc_unwarping,
        use_textline_orientation=args.use_textline_orientation,
        text_rec_score_thresh=args.text_rec_score_thresh,
        return_word_box=args.return_word_box,
    )


def json_default(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return value.tolist()
    if hasattr(value, "item"):
        return value.item()
    return str(value)


def result_to_json(result: Any) -> Any:
    if hasattr(result, "json"):
        return result.json
    if isinstance(result, dict):
        return result
    return {"raw": result}


def extract_texts(result_jsons: list[Any]) -> list[str]:
    parts: list[str] = []
    for fallback_index, item in enumerate(result_jsons, start=1):
        result = item.get("res", item) if isinstance(item, dict) else {}
        page_index = result.get("page_index")
        page_label = str(fallback_index if page_index is None else int(page_index) + 1)
        texts = result.get("rec_texts") or []
        if texts:
            parts.append(f"===== 第 {page_label} 页 =====")
            parts.extend(str(text) for text in texts)
    return parts


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", prefix=f".{path.name}.", dir=path.parent, delete=False) as handle:
        handle.write(text)
        temporary = Path(handle.name)
    temporary.replace(path)


def quality_report(rows: list[dict[str, str]]) -> str:
    failures = [row for row in rows if row["status"] == "failed"]
    low = [row for row in rows if row["status"] == "ok" and int(row["chars"]) < 20]
    lines = [
        "# PaddleOCR质检报告",
        "",
        f"- 文件：{len(rows)}",
        f"- 失败：{len(failures)}",
        f"- 低文本：{len(low)}",
        "- 该路线只生成文本和 JSON，不替代最终可搜索 PDF。",
        "",
    ]
    lines.extend(f"- {row['status']}：{row['source']}；{row['note']}".rstrip("；") for row in rows)
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cache_dir = resolve_cache_dir(args.cache_dir)
    os.environ["PADDLE_PDX_CACHE_HOME"] = str(cache_dir)
    maybe_reexec(cache_dir)
    if args.check_tools:
        return 0 if print_status(cache_dir) else 2
    if not args.paths:
        print("请提供 PDF、图片或文件夹，或使用 --check-tools。", file=sys.stderr)
        return 2
    missing_packages = [name for name in ("paddlepaddle", "paddleocr") if package_version(name) is None]
    if missing_packages:
        print("缺少 PaddleOCR 依赖：" + ", ".join(missing_packages), file=sys.stderr)
        return 2

    files = find_inputs(args.paths, recursive=not args.no_recursive)
    if not files:
        print("没有找到可识别文件；未创建任何成果。", file=sys.stderr)
        return 2
    root = common_root(args.paths)
    if root == Path("/") and not args.output_dir:
        print("输入跨越多个顶层目录；请显式指定 --output-dir。", file=sys.stderr)
        return 2
    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else root / "OCR成果"
    files = [path for path in files if not is_under(path, output_dir) and not path.name.endswith("_OCR.pdf")]
    if args.max_files:
        files = files[: args.max_files]
    if not files:
        print("没有找到需要处理的原始文件；未创建任何成果。", file=sys.stderr)
        return 2

    ensure_cache(cache_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    engine = build_ocr(args)
    rows: list[dict[str, str]] = []
    failed = False
    for index, source in enumerate(files, start=1):
        text_path, json_path = output_paths(source, root, output_dir)
        print(f"[{index}/{len(files)}] {source}")
        if text_path.exists() and json_path.exists() and not args.overwrite:
            rows.append({"source": str(source), "status": "exists", "chars": "0", "note": "沿用已有成果"})
            continue
        started = time.monotonic()
        try:
            results = engine.predict(str(source))
            result_jsons = [result_to_json(result) for result in results]
            text = "\n".join(extract_texts(result_jsons)).strip()
            atomic_write_text(json_path, json.dumps(result_jsons, ensure_ascii=False, indent=2, default=json_default) + "\n")
            atomic_write_text(text_path, text + ("\n" if text else ""))
            note = f"{time.monotonic() - started:.1f}秒"
            if len(text) < 20:
                note += "；文字偏少，须人工核对"
            rows.append({"source": str(source), "status": "ok", "chars": str(len(text)), "note": note})
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            failed = True
            rows.append({"source": str(source), "status": "failed", "chars": "0", "note": str(exc)})

    report = output_dir / "PaddleOCR质检报告.md"
    atomic_write_text(report, quality_report(rows))
    print(f"成果：{output_dir}")
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
