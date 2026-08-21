#!/usr/bin/env python3
"""Create searchable legal-case PDFs and a concise QA report."""

from __future__ import annotations

import argparse
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
    for bundled in (
        Path.home() / ".case-pdf-ocr/venv/lib",
        Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/python/lib",
    ):
        for site_packages in bundled.glob("python*/site-packages"):
            sys.path.append(str(site_packages))
    try:
        from pypdf import PdfReader as reader

        return reader
    except Exception:  # pragma: no cover - depends on the host environment
        return None


PdfReader = load_pdf_reader()


@dataclass
class PdfStats:
    pages: int | None
    sample_text_chars: int
    error: str = ""


def tool_path(name: str) -> str:
    return shutil.which(name) or ""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create searchable PDF copies in one OCR成果 directory.")
    parser.add_argument("paths", nargs="*", help="PDF files or folders")
    parser.add_argument("--mode", choices=("scan-only", "skip-text", "redo-ocr", "force-ocr"), default="skip-text")
    parser.add_argument("--profile", choices=("balanced", "fast", "careful", "troubleshoot"), default="balanced")
    parser.add_argument("--languages", default="chi_sim+eng")
    parser.add_argument("--output-dir", help="default: <input root>/OCR成果")
    parser.add_argument("--jobs", type=int)
    parser.add_argument("--optimize", type=int)
    parser.add_argument("--output-type", choices=("pdf", "pdfa", "pdfa-1", "pdfa-2", "pdfa-3"))
    parser.add_argument("--file-timeout", type=int, help="0 disables the whole-file timeout")
    parser.add_argument("--tesseract-timeout", type=int)
    parser.add_argument("--tesseract-non-ocr-timeout", type=int)
    parser.add_argument("--sanitize-input", choices=("auto", "always", "never"), default="auto")
    parser.add_argument("--max-files", type=int)
    parser.add_argument("--sample-pages", type=int, default=3)
    parser.add_argument("--no-recursive", action="store_true")
    parser.add_argument("--no-sidecar-text", action="store_true")
    parser.add_argument("--no-pdf-check", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--no-deskew", action="store_true")
    parser.add_argument("--no-rotate-pages", action="store_true")
    parser.add_argument("--clean-final", action="store_true", default=None)
    parser.add_argument("--check-tools", action="store_true")
    args = parser.parse_args(argv)
    validate_numeric_args(parser, args)
    apply_profile_defaults(args)
    return args


def validate_numeric_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    positive = ("jobs", "max_files", "sample_pages", "tesseract_timeout", "tesseract_non_ocr_timeout")
    for name in positive:
        value = getattr(args, name)
        if value is not None and value <= 0:
            parser.error(f"--{name.replace('_', '-')} must be greater than 0")
    if args.file_timeout is not None and args.file_timeout < 0:
        parser.error("--file-timeout must be 0 or greater")
    if args.optimize is not None and not 0 <= args.optimize <= 3:
        parser.error("--optimize must be between 0 and 3")


def apply_profile_defaults(args: argparse.Namespace) -> None:
    if args.profile == "fast":
        args.jobs = args.jobs or 4
        args.optimize = 0 if args.optimize is None else args.optimize
        args.output_type = args.output_type or "pdf"
        args.file_timeout = 0 if args.file_timeout is None else args.file_timeout
        args.tesseract_timeout = args.tesseract_timeout or 30
        args.tesseract_non_ocr_timeout = args.tesseract_non_ocr_timeout or 5
        args.no_deskew = True
        args.no_rotate_pages = True
    elif args.profile == "troubleshoot":
        args.jobs = args.jobs or 1
        args.optimize = 0 if args.optimize is None else args.optimize
        args.output_type = args.output_type or "pdf"
        args.file_timeout = 0 if args.file_timeout is None else args.file_timeout
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
    if args.mode == "redo-ocr":
        args.no_deskew = True
        args.no_rotate_pages = True
        args.clean_final = False


def dependency_status() -> dict[str, str]:
    return {name: tool_path(name) for name in ("ocrmypdf", "tesseract", "gs", "qpdf")}


def tesseract_has_language(language: str) -> bool:
    executable = tool_path("tesseract")
    if not executable:
        return False
    proc = subprocess.run([executable, "--list-langs"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return proc.returncode == 0 and language in {line.strip() for line in proc.stdout.splitlines()}


def print_dependency_status() -> bool:
    status = dependency_status()
    for name, path in status.items():
        print(f"{name}: {path or 'MISSING'}")
    chinese = tesseract_has_language("chi_sim")
    print(f"tesseract language chi_sim: {'ok' if chinese else 'MISSING'}")
    print(f"unpaper (optional): {tool_path('unpaper') or 'MISSING'}")
    return all(status.values()) and chinese


def find_pdfs(paths: Iterable[str], recursive: bool) -> list[Path]:
    pdfs: list[Path] = []
    for raw in paths:
        path = Path(raw).expanduser().resolve()
        if path.is_file() and path.suffix.lower() == ".pdf":
            pdfs.append(path)
        elif path.is_dir():
            iterator = path.rglob("*") if recursive else path.glob("*")
            pdfs.extend(p.resolve() for p in iterator if p.is_file() and p.suffix.lower() == ".pdf")
    return sorted(dict.fromkeys(pdfs))


def is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def common_root(paths: list[str]) -> Path:
    roots = []
    for raw in paths:
        path = Path(raw).expanduser().resolve()
        roots.append(str(path if path.is_dir() else path.parent))
    return Path(os.path.commonpath(roots)).resolve()


def sample_indexes(page_count: int, sample_pages: int) -> list[int]:
    if page_count <= 0:
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
                if reader.decrypt("") == 0:
                    return PdfStats(None, 0, "encrypted")
            except Exception:
                return PdfStats(None, 0, "encrypted")
        pages = len(reader.pages)
        chars = sum(len((reader.pages[index].extract_text() or "").strip()) for index in sample_indexes(pages, sample_pages))
        return PdfStats(pages, chars)
    except Exception as exc:
        return PdfStats(None, 0, f"invalid PDF: {exc}")


def relative_output_path(pdf: Path, root: Path, output_dir: Path) -> Path:
    try:
        rel = pdf.relative_to(root)
    except ValueError:
        rel = Path(pdf.name)
    target = output_dir / rel
    return target.with_name(f"{target.stem}_OCR.pdf")


def ocr_command(args: argparse.Namespace, src: Path, dst: Path) -> list[str]:
    cmd = ["ocrmypdf", "-l", args.languages, f"--{args.mode}", "--jobs", str(args.jobs), "--optimize", str(args.optimize)]
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
    proc = subprocess.Popen(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
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


def sanitize_pdf(src: Path, work_dir: Path) -> tuple[Path | None, str]:
    sanitized = work_dir / f"{src.stem}.sanitized.pdf"
    proc = subprocess.run(["qpdf", "--empty", "--pages", str(src), "--", str(sanitized)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    detail = ((proc.stderr or "") + "\n" + (proc.stdout or "")).strip()
    return (sanitized if proc.returncode == 0 else None), detail


def run_ocr_attempt(args: argparse.Namespace, src: Path, dst: Path) -> tuple[int, str, str, Path | None]:
    dst.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=f".{dst.stem}.", suffix=".partial.pdf", dir=dst.parent, delete=False) as handle:
        partial = Path(handle.name)
    try:
        code, stdout, stderr, timeout_note = run_process(ocr_command(args, src, partial), args.file_timeout or 0)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    detail = "\n".join(part for part in (timeout_note, stderr.strip(), stdout.strip()) if part)
    if code != 0:
        partial.unlink(missing_ok=True)
        partial = None
    return code, timeout_note, detail, partial


def run_ocr(args: argparse.Namespace, src: Path, dst: Path, work_dir: Path) -> tuple[str, str, Path | None]:
    if args.sanitize_input == "always":
        sanitized, detail = sanitize_pdf(src, work_dir)
        if sanitized is None:
            return "failed", f"qpdf sanitize failed: {detail}", None
        code, timeout_note, detail, candidate = run_ocr_attempt(args, sanitized, dst)
    else:
        code, timeout_note, detail, candidate = run_ocr_attempt(args, src, dst)
        if code != 0 and args.sanitize_input == "auto":
            sanitized, sanitize_detail = sanitize_pdf(src, work_dir)
            if sanitized is not None:
                code, timeout_note, detail, candidate = run_ocr_attempt(args, sanitized, dst)
            else:
                detail = f"{detail}\nqpdf sanitize failed: {sanitize_detail}".strip()
    if code == 0:
        return "ok", "", candidate
    return ("timeout" if timeout_note else "failed"), concise_error(detail or f"ocrmypdf exited {code}"), None


def concise_error(text: str, limit: int = 500) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"


def extract_text(pdf: Path) -> tuple[str, str]:
    if PdfReader is None:
        return "", "Python package pypdf is missing"
    try:
        reader = PdfReader(str(pdf))
        parts = [f"## 第 {number} 页\n\n{page.extract_text() or ''}" for number, page in enumerate(reader.pages, start=1)]
        return "\n\n".join(parts).strip() + "\n", ""
    except Exception as exc:
        return "", str(exc)


def page_text_rows(pdf: Path) -> tuple[list[dict[str, str]], str]:
    if PdfReader is None:
        return [], "Python package pypdf is missing"
    try:
        reader = PdfReader(str(pdf))
        rows = []
        for number, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            rows.append({"pdf": str(pdf), "page": str(number), "chars": str(len(text)), "sample": " ".join(text.split())[:80]})
        return rows, ""
    except Exception as exc:
        return [], str(exc)


def qpdf_check(pdf: Path) -> tuple[bool, str]:
    proc = subprocess.run(["qpdf", "--check", str(pdf)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return proc.returncode == 0, concise_error((proc.stderr or "") + "\n" + (proc.stdout or ""))


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", prefix=f".{path.name}.", dir=path.parent, delete=False) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    temporary.replace(path)


def qa_report(rows: list[dict[str, str]], pages: list[dict[str, str]]) -> str:
    failures = [row for row in rows if row["status"] not in {"ok", "exists", "scan-only"}]
    low_pages = [row for row in pages if int(row["chars"]) < 20]
    lines = [
        "# OCR质检报告",
        "",
        f"- 文件：{len(rows)}",
        f"- 失败：{len(failures)}",
        f"- 逐页低文本：{len(low_pages)}",
        "- 低文本、签章、手写、表格和印章页仍须对照原图人工复核。",
        "",
        "## 文件结果",
        "",
    ]
    for row in rows:
        detail = f"；{row['note']}" if row.get("note") else ""
        lines.append(f"- {row['status']}：{row['source']} → {row.get('output') or '未生成'}{detail}")
    if low_pages:
        lines.extend(["", "## 低文本页面", ""])
        lines.extend(f"- 第{row['page']}页，{row['chars']}字：{row['pdf']} {row['sample']}".rstrip() for row in low_pages[:200])
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.check_tools:
        return 0 if print_dependency_status() else 2
    if not args.paths:
        print("请提供 PDF 文件或文件夹，或使用 --check-tools。", file=sys.stderr)
        return 2

    pdfs = find_pdfs(args.paths, recursive=not args.no_recursive)
    if not pdfs:
        print("没有找到 PDF；未创建任何成果。", file=sys.stderr)
        return 2
    root = common_root(args.paths)
    if root == Path("/") and not args.output_dir:
        print("输入跨越多个顶层目录；请显式指定 --output-dir。", file=sys.stderr)
        return 2
    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else root / "OCR成果"
    pdfs = [pdf for pdf in pdfs if not is_under(pdf, output_dir) and not pdf.name.endswith("_OCR.pdf")]
    if args.max_files:
        pdfs = pdfs[: args.max_files]
    if not pdfs:
        print("没有找到需要处理的原始 PDF；未创建任何成果。", file=sys.stderr)
        return 2

    if args.mode != "scan-only":
        missing_tools = [name for name, path in dependency_status().items() if not path]
        if not tesseract_has_language("chi_sim"):
            missing_tools.append("tesseract:chi_sim")
        if missing_tools:
            print("缺少必需 OCR 工具：" + ", ".join(missing_tools), file=sys.stderr)
            return 2
    if PdfReader is None:
        print("缺少 Python 包 pypdf；安装后重试。", file=sys.stderr)
        return 2

    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str]] = []
    all_page_rows: list[dict[str, str]] = []
    hard_failure = False
    with tempfile.TemporaryDirectory(prefix="case-ocr-") as temporary:
        work_dir = Path(temporary)
        for index, src in enumerate(pdfs, start=1):
            dst = relative_output_path(src, root, output_dir)
            before = inspect_pdf(src, args.sample_pages)
            row = {"source": str(src), "output": "", "status": "scan-only", "note": before.error}
            print(f"[{index}/{len(pdfs)}] {src}", flush=True)
            if before.error:
                row["status"] = "encrypted" if before.error == "encrypted" else "failed"
                hard_failure = True
                rows.append(row)
                continue
            if args.mode == "scan-only":
                page_rows, error = page_text_rows(src)
                all_page_rows.extend(page_rows)
                if error:
                    row["status"] = "failed"
                    row["note"] = error
                    hard_failure = True
                rows.append(row)
                continue

            candidate: Path | None = None
            try:
                if dst.exists() and not args.overwrite:
                    row["status"] = "exists"
                    row["note"] = "沿用已有成果；传 --overwrite 才重做"
                    row["output"] = str(dst)
                else:
                    status, note, candidate = run_ocr(args, src, dst, work_dir)
                    row["status"], row["note"] = status, note
                    if status != "ok":
                        hard_failure = True
                        rows.append(row)
                        continue

                check_pdf = candidate or dst
                after = inspect_pdf(check_pdf, args.sample_pages)
                if after.error or after.pages != before.pages:
                    row["status"] = "failed-check"
                    row["note"] = after.error or f"页数变化：{before.pages} → {after.pages}"
                    hard_failure = True
                elif after.sample_text_chars < 20:
                    row["note"] = "抽样文字偏少，须人工核对"

                if not args.no_pdf_check and row["status"] in {"ok", "exists"}:
                    valid, detail = qpdf_check(check_pdf)
                    if not valid:
                        row["status"] = "failed-check"
                        row["note"] = f"qpdf 检查失败：{detail}"
                        hard_failure = True

                if row["status"] in {"ok", "exists"} and candidate is not None:
                    try:
                        candidate.replace(dst)
                        candidate = None
                        row["output"] = str(dst)
                    except OSError as exc:
                        row["status"] = "failed-check"
                        row["note"] = f"成果写入失败：{exc}"
                        hard_failure = True

                if not args.no_sidecar_text and row["status"] in {"ok", "exists"}:
                    content, error = extract_text(dst)
                    if error:
                        row["status"] = "failed-check"
                        row["note"] = f"Markdown 提取失败：{error}"
                        hard_failure = True
                    else:
                        atomic_write_text(dst.with_suffix(".md"), content)
                if row["status"] in {"ok", "exists"}:
                    page_rows, error = page_text_rows(dst)
                    all_page_rows.extend(page_rows)
                    if error:
                        row["status"] = "failed-check"
                        row["note"] = f"逐页文字检查失败：{error}"
                        hard_failure = True
                rows.append(row)
            finally:
                if candidate is not None:
                    candidate.unlink(missing_ok=True)

    report = output_dir / "OCR质检报告.md"
    atomic_write_text(report, qa_report(rows, all_page_rows))
    print(f"成果：{output_dir}")
    print(f"质检：{report}")
    return 1 if hard_failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
