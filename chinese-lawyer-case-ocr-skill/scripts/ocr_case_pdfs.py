#!/usr/bin/env python3
"""Batch scan and OCR legal-case PDFs with OCRmyPDF."""

from __future__ import annotations

import argparse
import csv
import os
import signal
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


def load_pdf_reader():
    try:
        from pypdf import PdfReader as reader

        return reader
    except Exception:
        pass
    bundled = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/python/lib"
    for site_packages in bundled.glob("python*/site-packages"):
        sys.path.append(str(site_packages))
    try:
        from pypdf import PdfReader as reader

        return reader
    except Exception:  # pragma: no cover - dependency check is runtime-specific
        return None


PdfReader = load_pdf_reader()


@dataclass
class PdfStats:
    pages: int | None
    sample_text_chars: int
    error: str = ""


MANIFEST_FIELDS = [
    "source",
    "output",
    "status",
    "pages_before",
    "sample_text_chars_before",
    "pages_after",
    "sample_text_chars_after",
    "log",
    "note",
]

SIDECAR_FIELDS = ["pdf", "text", "status", "chars", "note"]

PDF_CHECK_FIELDS = ["pdf", "status", "note"]

PAGE_TEXT_FIELDS = ["pdf", "page", "chars", "rotation", "width", "height", "sample", "note"]


def tool_path(name: str) -> str:
    return shutil.which(name) or ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inventory and OCR PDFs into searchable copies with QA reports.",
    )
    parser.add_argument("paths", nargs="*", help="PDF files or folders to process")
    parser.add_argument(
        "--mode",
        choices=("scan-only", "skip-text", "redo-ocr", "force-ocr"),
        default="skip-text",
        help="scan-only reports only; other modes call OCRmyPDF",
    )
    parser.add_argument("--languages", default="chi_sim+eng", help="Tesseract languages")
    parser.add_argument(
        "--profile",
        choices=("balanced", "fast", "careful", "troubleshoot"),
        default="balanced",
        help="OCR parameter profile: balanced default, fast bulk attachments, careful core evidence, troubleshoot stubborn PDFs",
    )
    parser.add_argument("--output-dir", help="Directory for OCR PDF copies")
    parser.add_argument("--report-dir", help="Directory for manifest and logs")
    parser.add_argument("--text-dir", help="Directory for extracted OCR text sidecars")
    parser.add_argument("--jobs", type=int, help="OCRmyPDF job count")
    parser.add_argument("--optimize", type=int, help="OCRmyPDF optimize level")
    parser.add_argument("--output-type", choices=("pdf", "pdfa", "pdfa-1", "pdfa-2", "pdfa-3"), help="OCRmyPDF output type")
    parser.add_argument("--file-timeout", type=int, help="Seconds before stopping one OCR file; 0 disables")
    parser.add_argument("--tesseract-timeout", type=int, help="Seconds before Tesseract gives up on one page")
    parser.add_argument("--tesseract-non-ocr-timeout", type=int, help="Seconds before Tesseract gives up deciding a page has no OCR")
    parser.add_argument(
        "--sanitize-input",
        choices=("auto", "always", "never"),
        default="auto",
        help="Use qpdf to rebuild page content before OCR: auto retries failures, always prevents bad metadata failures, never disables",
    )
    parser.add_argument("--max-files", type=int, help="Process only the first N PDFs")
    parser.add_argument("--sample-pages", type=int, default=3, help="Pages to sample for text")
    parser.add_argument("--no-recursive", action="store_true", help="Do not recurse folders")
    parser.add_argument("--no-resume", action="store_true", help="Do not skip prior ok/existing manifest rows")
    parser.add_argument("--no-sidecar-text", action="store_true", help="Do not extract TXT sidecars from OCR outputs")
    parser.add_argument("--no-pdf-check", action="store_true", help="Do not run qpdf --check on OCR outputs")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing outputs")
    parser.add_argument("--no-deskew", action="store_true", help="Disable OCRmyPDF deskew")
    parser.add_argument("--no-rotate-pages", action="store_true", help="Disable auto-rotation")
    parser.add_argument("--clean-final", action="store_true", default=None, help="Pass --clean-final")
    parser.add_argument(
        "--check-tools",
        action="store_true",
        help="Print dependency status and exit without scanning PDFs",
    )
    args = parser.parse_args()
    apply_profile_defaults(args)
    return args


def apply_profile_defaults(args: argparse.Namespace) -> None:
    if args.profile == "fast":
        args.jobs = args.jobs or 4
        args.optimize = 0 if args.optimize is None else args.optimize
        args.output_type = args.output_type or "pdf"
        args.file_timeout = 240 if args.file_timeout is None else args.file_timeout
        args.tesseract_timeout = args.tesseract_timeout or 8
        args.tesseract_non_ocr_timeout = args.tesseract_non_ocr_timeout or 5
        args.no_deskew = True
        args.no_rotate_pages = True
    elif args.profile == "troubleshoot":
        args.jobs = args.jobs or 1
        args.optimize = 0 if args.optimize is None else args.optimize
        args.output_type = args.output_type or "pdf"
        args.file_timeout = 600 if args.file_timeout is None else args.file_timeout
        args.tesseract_timeout = args.tesseract_timeout or 30
        args.tesseract_non_ocr_timeout = args.tesseract_non_ocr_timeout or 10
        if args.sanitize_input == "auto":
            args.sanitize_input = "always"
    else:
        args.jobs = args.jobs or 2
        args.optimize = 1 if args.optimize is None else args.optimize
        args.file_timeout = 0 if args.file_timeout is None else args.file_timeout
        if args.clean_final is None:
            args.clean_final = args.profile == "careful" and bool(tool_path("unpaper"))

    if args.clean_final is None:
        args.clean_final = False


def dependency_status(include_unpaper: bool = False) -> dict[str, str]:
    names = ["ocrmypdf", "tesseract", "gs", "qpdf"]
    if include_unpaper:
        names.append("unpaper")
    return {name: tool_path(name) for name in names}


def print_dependency_status() -> None:
    for name, path in dependency_status().items():
        print(f"{name}: {path or 'MISSING'}")
    print(f"unpaper (optional for --clean-final): {tool_path('unpaper') or 'MISSING'}")


def find_pdfs(paths: Iterable[str], recursive: bool) -> list[Path]:
    pdfs: list[Path] = []
    for raw in paths:
        path = Path(raw).expanduser().resolve()
        if path.is_file() and path.suffix.lower() == ".pdf":
            pdfs.append(path)
        elif path.is_dir():
            iterator = path.rglob("*.pdf") if recursive else path.glob("*.pdf")
            pdfs.extend(p.resolve() for p in iterator if p.is_file())
    return sorted(dict.fromkeys(pdfs))


def common_root(paths: list[str], pdfs: list[Path]) -> Path:
    roots: list[str] = []
    for raw in paths:
        path = Path(raw).expanduser().resolve()
        roots.append(str(path if path.is_dir() else path.parent))
    if not roots and pdfs:
        roots = [str(pdfs[0].parent)]
    return Path(os.path.commonpath(roots)).resolve()


def default_output_dirs(root: Path, args: argparse.Namespace) -> tuple[Path, Path]:
    process_dir = root / "OCR过程文件"
    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else root / "OCR成果：可检索PDF"
    report_dir = Path(args.report_dir).expanduser().resolve() if args.report_dir else process_dir / "OCR报告"
    return output_dir, report_dir


def default_text_dir(root: Path, args: argparse.Namespace) -> Path:
    if args.text_dir:
        return Path(args.text_dir).expanduser().resolve()
    return root / "OCR过程文件" / "OCR文本"


def should_exclude(pdf: Path, output_dir: Path, report_dir: Path, process_dir: Path) -> bool:
    excluded_roots = (output_dir.resolve(), process_dir.resolve(), report_dir.resolve())
    for root in excluded_roots:
        try:
            pdf.relative_to(root)
            return True
        except ValueError:
            pass
    return pdf.name.endswith("_OCR.pdf")


def sample_indexes(page_count: int, sample_pages: int) -> list[int]:
    if page_count <= 0 or sample_pages <= 0:
        return []
    candidates = {0, page_count - 1, page_count // 2}
    if sample_pages > 3:
        step = max(1, page_count // sample_pages)
        candidates.update(range(0, page_count, step))
    return sorted(i for i in candidates if 0 <= i < page_count)[:sample_pages]


def inspect_pdf(path: Path, sample_pages: int) -> PdfStats:
    if PdfReader is None:
        return PdfStats(None, 0, "Python package pypdf is missing")
    try:
        reader = PdfReader(str(path))
        if getattr(reader, "is_encrypted", False):
            try:
                reader.decrypt("")
            except Exception:
                return PdfStats(None, 0, "encrypted")
        pages = len(reader.pages)
        chars = 0
        for index in sample_indexes(pages, sample_pages):
            text = reader.pages[index].extract_text() or ""
            chars += len(text.strip())
        return PdfStats(pages, chars)
    except Exception as exc:
        return PdfStats(None, 0, str(exc))


def relative_output_path(pdf: Path, root: Path, output_dir: Path) -> Path:
    try:
        rel = pdf.relative_to(root)
    except ValueError:
        rel = Path(pdf.name)
    target = output_dir / rel
    return target.with_name(f"{target.stem}_OCR.pdf")


def ocr_command(args: argparse.Namespace, src: Path, dst: Path) -> list[str]:
    cmd = [
        "ocrmypdf",
        "-l",
        args.languages,
        f"--{args.mode}",
        "--jobs",
        str(args.jobs),
        "--optimize",
        str(args.optimize),
    ]
    if args.output_type:
        cmd.extend(["--output-type", args.output_type])
    if args.tesseract_timeout:
        cmd.extend(["--tesseract-timeout", str(args.tesseract_timeout)])
    if args.tesseract_non_ocr_timeout:
        cmd.extend(["--tesseract-non-ocr-timeout", str(args.tesseract_non_ocr_timeout)])
    if not args.no_deskew:
        cmd.append("--deskew")
    if not args.no_rotate_pages:
        cmd.append("--rotate-pages")
    if args.clean_final:
        cmd.append("--clean-final")
    cmd.extend([str(src), str(dst)])
    return cmd


def run_process(cmd: list[str], timeout: int) -> tuple[int, str, str, str]:
    proc = subprocess.Popen(
        cmd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout or None)
        return proc.returncode, stdout or "", stderr or "", ""
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            stdout, stderr = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            stdout, stderr = proc.communicate()
        return 124, stdout or "", stderr or "", f"timeout after {timeout} seconds"


def sanitize_pdf(src: Path, dst_dir: Path, stem: str) -> tuple[Path | None, str]:
    if not tool_path("qpdf"):
        return None, "qpdf missing; cannot sanitize input\n"
    with tempfile.NamedTemporaryFile(
        prefix=stem + ".sanitized.",
        suffix=".pdf",
        dir=str(dst_dir),
        delete=False,
    ) as tmp:
        sanitized = Path(tmp.name)
    cmd = ["qpdf", "--empty", "--pages", str(src), "--", str(sanitized)]
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    log = (
        "$ "
        + " ".join(cmd)
        + f"\nQPDF return code: {proc.returncode}\nQPDF STDOUT:\n"
        + (proc.stdout or "")
        + "\nQPDF STDERR:\n"
        + (proc.stderr or "")
        + "\n"
    )
    if proc.returncode != 0:
        sanitized.unlink(missing_ok=True)
        return None, log
    return sanitized, log


def run_ocr_attempt(args: argparse.Namespace, src: Path, dst: Path, log_parts: list[str], label: str) -> tuple[int, str]:
    with tempfile.NamedTemporaryFile(
        prefix=dst.stem + ".",
        suffix=".partial.pdf",
        dir=str(dst.parent),
        delete=False,
    ) as tmp:
        tmp_path = Path(tmp.name)
    cmd = ocr_command(args, src, tmp_path)
    returncode, stdout, stderr, timeout_note = run_process(cmd, args.file_timeout or 0)
    log_parts.append(
        f"## Attempt: {label}\n$ "
        + " ".join(cmd)
        + f"\nReturn code: {returncode}\n"
        + (f"{timeout_note}\n" if timeout_note else "")
        + "\nSTDOUT:\n"
        + stdout
        + "\nSTDERR:\n"
        + stderr
        + "\n"
    )
    if returncode == 0:
        tmp_path.replace(dst)
    else:
        tmp_path.unlink(missing_ok=True)
    return returncode, timeout_note


def run_ocr(args: argparse.Namespace, src: Path, dst: Path, log_path: Path) -> tuple[str, str]:
    dst.parent.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_parts: list[str] = []
    sanitized: Path | None = None
    try:
        if args.sanitize_input == "always":
            sanitized, qpdf_log = sanitize_pdf(src, dst.parent, dst.stem)
            log_parts.append(qpdf_log)
            if sanitized is None:
                log_path.write_text("\n".join(log_parts), encoding="utf-8")
                return "failed", "qpdf sanitize failed"
            returncode, timeout_note = run_ocr_attempt(args, sanitized, dst, log_parts, "sanitized")
        else:
            returncode, timeout_note = run_ocr_attempt(args, src, dst, log_parts, "original")
            if returncode != 0 and args.sanitize_input == "auto":
                sanitized, qpdf_log = sanitize_pdf(src, dst.parent, dst.stem)
                log_parts.append(qpdf_log)
                if sanitized is not None:
                    returncode, timeout_note = run_ocr_attempt(args, sanitized, dst, log_parts, "sanitized-retry")
        log_path.write_text("\n".join(log_parts), encoding="utf-8")
        if returncode == 0:
            return "ok", ""
        if timeout_note:
            return "timeout", timeout_note
        return "failed", f"ocrmypdf exited {returncode}"
    finally:
        if sanitized is not None:
            sanitized.unlink(missing_ok=True)


def write_manifest(report_dir: Path, rows: list[dict[str, str]]) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    with (report_dir / "ocr_manifest.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    failures = [row for row in rows if row["status"] not in {"ok", "exists", "scan-only"}]
    failed_path = report_dir / "failed_pdfs.txt"
    if failures:
        with failed_path.open("w", encoding="utf-8") as handle:
            for row in failures:
                handle.write(f"{row['status']}\t{row['source']}\t{row['note']}\n")
    elif failed_path.exists():
        failed_path.unlink()


def read_manifest(report_dir: Path) -> dict[str, dict[str, str]]:
    path = report_dir / "ocr_manifest.csv"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8-sig") as handle:
        return {row["source"]: row for row in csv.DictReader(handle)}


def extract_text(pdf: Path) -> tuple[str, str]:
    if PdfReader is None:
        return "", "Python package pypdf is missing"
    try:
        reader = PdfReader(str(pdf))
        parts: list[str] = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            parts.append(f"\n\n===== Page {page_number} =====\n{text}")
        return ("".join(parts).strip() + "\n"), ""
    except Exception as exc:
        return "", str(exc)


def extract_page_text_rows(pdf: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if PdfReader is None:
        return [
            {
                "pdf": str(pdf),
                "page": "",
                "chars": "0",
                "rotation": "",
                "width": "",
                "height": "",
                "sample": "",
                "note": "Python package pypdf is missing",
            }
        ]
    try:
        reader = PdfReader(str(pdf))
        for page_number, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            sample = " ".join(text.split())[:120]
            chars = len(text)
            rows.append(
                {
                    "pdf": str(pdf),
                    "page": str(page_number),
                    "chars": str(chars),
                    "rotation": str(int(getattr(page, "rotation", 0) or 0)),
                    "width": f"{float(page.mediabox.width):.1f}",
                    "height": f"{float(page.mediabox.height):.1f}",
                    "sample": sample,
                    "note": "low page text; inspect visually" if chars < 20 else "",
                }
            )
    except Exception as exc:
        rows.append(
            {
                "pdf": str(pdf),
                "page": "",
                "chars": "0",
                "rotation": "",
                "width": "",
                "height": "",
                "sample": "",
                "note": str(exc),
            }
        )
    return rows


def write_page_text_manifest(report_dir: Path, rows: list[dict[str, str]]) -> list[dict[str, str]]:
    page_rows: list[dict[str, str]] = []
    seen: set[Path] = set()
    for row in rows:
        if row["status"] in {"ok", "exists"} and row.get("output"):
            pdf = Path(row["output"])
        elif row["status"] == "scan-only":
            pdf = Path(row["source"])
        else:
            continue
        if pdf in seen or not pdf.exists():
            continue
        seen.add(pdf)
        page_rows.extend(extract_page_text_rows(pdf))
    report_dir.mkdir(parents=True, exist_ok=True)
    with (report_dir / "page_text_manifest.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=PAGE_TEXT_FIELDS)
        writer.writeheader()
        writer.writerows(page_rows)
    return page_rows


def sidecar_text_path(pdf: Path, output_dir: Path, text_dir: Path) -> Path:
    try:
        rel = pdf.relative_to(output_dir)
    except ValueError:
        rel = Path(pdf.name)
    return (text_dir / rel).with_suffix(".txt")


def write_sidecars(report_dir: Path, output_dir: Path, text_dir: Path, rows: list[dict[str, str]]) -> list[dict[str, str]]:
    sidecar_rows: list[dict[str, str]] = []
    for row in rows:
        if row["status"] not in {"ok", "exists"}:
            continue
        pdf = Path(row["output"])
        txt = sidecar_text_path(pdf, output_dir, text_dir)
        txt.parent.mkdir(parents=True, exist_ok=True)
        content, error = extract_text(pdf)
        status = "failed" if error else "ok"
        chars = len(content.strip())
        note = error
        if status == "ok":
            txt.write_text(content, encoding="utf-8")
            if chars < 20:
                note = "low extracted text; spot-check visually"
        sidecar_rows.append(
            {
                "pdf": str(pdf),
                "text": str(txt),
                "status": status,
                "chars": str(chars),
                "note": note,
            }
        )
    report_dir.mkdir(parents=True, exist_ok=True)
    with (report_dir / "sidecar_text_manifest.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=SIDECAR_FIELDS)
        writer.writeheader()
        writer.writerows(sidecar_rows)
    return sidecar_rows


def check_pdf_outputs(report_dir: Path, rows: list[dict[str, str]]) -> list[dict[str, str]]:
    check_rows: list[dict[str, str]] = []
    if not tool_path("qpdf"):
        check_rows.append({"pdf": "", "status": "skipped", "note": "qpdf missing"})
    else:
        for row in rows:
            if row["status"] not in {"ok", "exists"}:
                continue
            pdf = row.get("output") or ""
            result = subprocess.run(["qpdf", "--check", pdf], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            note = ((result.stderr or "") + "\n" + (result.stdout or "")).strip()
            check_rows.append(
                {
                    "pdf": pdf,
                    "status": "ok" if result.returncode == 0 else "failed",
                    "note": note,
                }
            )
    report_dir.mkdir(parents=True, exist_ok=True)
    with (report_dir / "pdf_check_manifest.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=PDF_CHECK_FIELDS)
        writer.writeheader()
        writer.writerows(check_rows)
    return check_rows


def write_quality_report(
    report_dir: Path,
    rows: list[dict[str, str]],
    sidecar_rows: list[dict[str, str]] | None,
    pdf_check_rows: list[dict[str, str]] | None,
    page_text_rows: list[dict[str, str]] | None,
) -> None:
    status_counts: dict[str, int] = {}
    for row in rows:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
    page_changes = [
        row
        for row in rows
        if row.get("pages_before")
        and row.get("pages_after")
        and row["pages_before"] != row["pages_after"]
    ]
    low_after = [
        row
        for row in rows
        if row["status"] in {"ok", "exists"}
        and (row.get("sample_text_chars_after") or "0").isdigit()
        and int(row.get("sample_text_chars_after") or 0) < 20
    ]
    failures = [row for row in rows if row["status"] not in {"ok", "exists", "scan-only"}]
    lines = [
        "# OCR质量检查",
        "",
        f"- 清单文件数：{len(rows)}",
        "- 状态统计：" + ", ".join(f"{key}={value}" for key, value in sorted(status_counts.items())),
        f"- 页数变化：{len(page_changes)}",
        f"- OCR 后抽样低文本：{len(low_after)}",
        f"- 失败/超时/加密：{len(failures)}",
    ]
    if page_text_rows is not None:
        low_page_text = [
            row
            for row in page_text_rows
            if row.get("chars", "0").isdigit() and int(row.get("chars", "0")) < 20
        ]
        landscape_pages = [
            row
            for row in page_text_rows
            if row.get("width")
            and row.get("height")
            and float(row["width"]) > float(row["height"]) * 1.08
        ]
        lines.extend(
            [
                f"- 逐页文字层检查：{len(page_text_rows)} 页",
                f"- 逐页低文本：{len(low_page_text)} 页",
                f"- 横向页面：{len(landscape_pages)} 页",
            ]
        )
    if sidecar_rows is not None:
        sidecar_failures = [row for row in sidecar_rows if row["status"] != "ok"]
        sidecar_low = [row for row in sidecar_rows if row["chars"].isdigit() and int(row["chars"]) < 20]
        lines.extend(
            [
                f"- 文本副本：{len(sidecar_rows)}",
                f"- 文本副本失败：{len(sidecar_failures)}",
                f"- 文本副本低文本：{len(sidecar_low)}",
            ]
        )
    if pdf_check_rows is not None:
        pdf_check_failed = [row for row in pdf_check_rows if row["status"] not in {"ok", "skipped"}]
        pdf_check_skipped = [row for row in pdf_check_rows if row["status"] == "skipped"]
        lines.extend(
            [
                f"- PDF 结构检查：{len(pdf_check_rows) - len(pdf_check_skipped)}",
                f"- PDF 结构检查失败：{len(pdf_check_failed)}",
            ]
        )
        if pdf_check_skipped:
            lines.append("- PDF 结构检查跳过：qpdf missing")
    if failures:
        lines.extend(["", "## 失败清单", ""])
        lines.extend(f"- {row['status']}: {row['source']} {row['note']}".rstrip() for row in failures[:100])
    if low_after:
        lines.extend(["", "## 低文本抽样清单", ""])
        lines.extend(f"- {row['source']}" for row in low_after[:100])
    if page_text_rows is not None:
        low_page_text = [
            row
            for row in page_text_rows
            if row.get("chars", "0").isdigit() and int(row.get("chars", "0")) < 20
        ]
        if low_page_text:
            lines.extend(["", "## 逐页低文本清单", ""])
            lines.extend(
                f"- 第{row['page']}页 chars={row['chars']}: {row['pdf']} {row['sample']}".rstrip()
                for row in low_page_text[:100]
            )
    if pdf_check_rows is not None:
        pdf_check_failed = [row for row in pdf_check_rows if row["status"] not in {"ok", "skipped"}]
        if pdf_check_failed:
            lines.extend(["", "## PDF结构检查失败清单", ""])
            lines.extend(f"- {row['pdf']} {row['note']}".rstrip() for row in pdf_check_failed[:100])
    (report_dir / "OCR质量检查.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    if args.check_tools:
        print_dependency_status()
        return 0
    if not args.paths:
        print("Provide at least one PDF file or folder, or use --check-tools.", file=sys.stderr)
        return 2

    pdfs = find_pdfs(args.paths, recursive=not args.no_recursive)
    if args.max_files:
        pdfs = pdfs[: args.max_files]
    root = common_root(args.paths, pdfs)
    output_dir, report_dir = default_output_dirs(root, args)
    text_dir = default_text_dir(root, args)
    process_dir = root / "OCR过程文件"
    pdfs = [p for p in pdfs if not should_exclude(p, output_dir, report_dir, process_dir)]

    missing = [name for name, path in dependency_status(include_unpaper=bool(args.clean_final)).items() if not path]
    if args.mode != "scan-only" and missing:
        print("Missing OCR tools: " + ", ".join(missing), file=sys.stderr)
        print("Run with --mode scan-only or install the missing tools.", file=sys.stderr)
        return 2

    existing_rows = read_manifest(report_dir) if not args.no_resume else {}
    rows: list[dict[str, str]] = []
    for index, src in enumerate(pdfs, start=1):
        dst = relative_output_path(src, root, output_dir)
        log_path = report_dir / "logs" / (dst.stem + ".log")
        existing = existing_rows.get(str(src))
        if (
            existing
            and args.mode != "scan-only"
            and not args.overwrite
            and existing.get("status") in {"ok", "exists"}
            and Path(existing.get("output") or dst).exists()
        ):
            rows.append(existing)
            print(f"[{index}/{len(pdfs)}] resume {src}")
            write_manifest(report_dir, rows)
            continue

        before = inspect_pdf(src, args.sample_pages)
        row = {
            "source": str(src),
            "output": str(dst),
            "status": "scan-only",
            "pages_before": "" if before.pages is None else str(before.pages),
            "sample_text_chars_before": str(before.sample_text_chars),
            "pages_after": "",
            "sample_text_chars_after": "",
            "log": "",
            "note": before.error,
        }
        print(f"[{index}/{len(pdfs)}] {src}")

        if args.mode == "scan-only":
            rows.append(row)
            write_manifest(report_dir, rows)
            continue
        if before.error == "encrypted":
            row["status"] = "encrypted"
            rows.append(row)
            write_manifest(report_dir, rows)
            continue
        if dst.exists() and not args.overwrite:
            row["status"] = "exists"
            row["note"] = "output exists; pass --overwrite to replace"
            rows.append(row)
            write_manifest(report_dir, rows)
            continue

        status, note = run_ocr(args, src, dst, log_path)
        row["status"] = status
        row["note"] = note
        row["log"] = str(log_path)
        if status == "ok":
            after = inspect_pdf(dst, args.sample_pages)
            row["pages_after"] = "" if after.pages is None else str(after.pages)
            row["sample_text_chars_after"] = str(after.sample_text_chars)
            if after.error:
                row["note"] = after.error
            elif after.sample_text_chars < 20:
                row["note"] = "low extracted text after OCR; spot-check visually"
        rows.append(row)
        write_manifest(report_dir, rows)

    write_manifest(report_dir, rows)
    page_text_rows = write_page_text_manifest(report_dir, rows)
    sidecar_rows = None
    if args.mode != "scan-only" and not args.no_sidecar_text:
        sidecar_rows = write_sidecars(report_dir, output_dir, text_dir, rows)
    pdf_check_rows = None
    if args.mode != "scan-only" and not args.no_pdf_check:
        pdf_check_rows = check_pdf_outputs(report_dir, rows)
    write_quality_report(report_dir, rows, sidecar_rows, pdf_check_rows, page_text_rows)
    print(f"PDFs scanned: {len(pdfs)}")
    print(f"Manifest: {report_dir / 'ocr_manifest.csv'}")
    if sidecar_rows is not None:
        print(f"Sidecar text manifest: {report_dir / 'sidecar_text_manifest.csv'}")
    if pdf_check_rows is not None:
        print(f"PDF check manifest: {report_dir / 'pdf_check_manifest.csv'}")
    print(f"Page text manifest: {report_dir / 'page_text_manifest.csv'}")
    print(f"Quality report: {report_dir / 'OCR质量检查.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
