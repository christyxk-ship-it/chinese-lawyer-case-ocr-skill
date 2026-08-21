from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "chinese-lawyer-case-ocr-skill" / "scripts"


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class MainOcrTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module("ocr_case_pdfs_test", "ocr_case_pdfs.py")

    def test_empty_directory_is_an_error_and_creates_no_results(self):
        with tempfile.TemporaryDirectory() as temporary, redirect_stderr(StringIO()):
            root = Path(temporary)
            self.assertEqual(self.module.main([str(root), "--mode", "scan-only"]), 2)
            self.assertFalse((root / "OCR成果").exists())

    def test_missing_tools_make_check_fail(self):
        missing = {name: "" for name in ("ocrmypdf", "tesseract", "gs", "qpdf")}
        with mock.patch.object(self.module, "dependency_status", return_value=missing), \
             mock.patch.object(self.module, "tesseract_has_language", return_value=False), \
             mock.patch.object(self.module, "tool_path", return_value=""), \
             redirect_stdout(StringIO()):
            self.assertEqual(self.module.main(["--check-tools"]), 2)

    def test_invalid_pdf_returns_failure_and_reports_it(self):
        with tempfile.TemporaryDirectory() as temporary, redirect_stdout(StringIO()):
            root = Path(temporary)
            (root / "broken.pdf").write_bytes(b"not a pdf")
            self.assertEqual(self.module.main([str(root), "--mode", "scan-only"]), 1)
            report = (root / "OCR成果" / "OCR质检报告.md").read_text(encoding="utf-8")
            self.assertIn("失败：1", report)

    def test_uppercase_pdf_is_discovered(self):
        with tempfile.TemporaryDirectory() as temporary:
            pdf = Path(temporary) / "SCAN.PDF"
            pdf.write_bytes(b"placeholder")
            self.assertEqual(self.module.find_pdfs([temporary], recursive=True), [pdf.resolve()])

    def test_redo_mode_disables_incompatible_image_processing(self):
        args = self.module.parse_args(["input.pdf", "--mode", "redo-ocr", "--profile", "careful"])
        command = self.module.ocr_command(args, Path("in.pdf"), Path("out.pdf"))
        self.assertNotIn("--deskew", command)
        self.assertNotIn("--rotate-pages", command)
        self.assertNotIn("--clean-final", command)

    def test_failed_replacement_preserves_existing_result(self):
        with tempfile.TemporaryDirectory() as temporary, redirect_stdout(StringIO()):
            root = Path(temporary)
            source = root / "source.pdf"
            source.write_bytes(b"source")
            result = root / "OCR成果" / "source_OCR.pdf"
            result.parent.mkdir()
            result.write_bytes(b"old-result")
            candidate_holder: list[Path] = []

            def fake_run_ocr(args, src, dst, work_dir):
                candidate = dst.parent / ".candidate.partial.pdf"
                candidate.write_bytes(b"new-result")
                candidate_holder.append(candidate)
                return "ok", "", candidate

            def fake_inspect(path, sample_pages):
                return self.module.PdfStats(1 if path.name == source.name else 2, 100)

            tools = {name: f"/{name}" for name in ("ocrmypdf", "tesseract", "gs", "qpdf")}
            with mock.patch.object(self.module, "dependency_status", return_value=tools), \
                 mock.patch.object(self.module, "tesseract_has_language", return_value=True), \
                 mock.patch.object(self.module, "inspect_pdf", side_effect=fake_inspect), \
                 mock.patch.object(self.module, "run_ocr", side_effect=fake_run_ocr):
                self.assertEqual(self.module.main([str(root), "--overwrite"]), 1)

            self.assertEqual(result.read_bytes(), b"old-result")
            self.assertFalse(candidate_holder[0].exists())


class PaddlePdfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["CASE_PDF_OCR_PADDLE_SEARCHABLE_REEXEC"] = "1"
        cls.module = load_module("paddle_searchable_pdf_test", "paddle_searchable_pdf.py")

    def test_page_ranges_are_strict(self):
        self.assertEqual(self.module.parse_pages("1-2,4", 5, None), {0, 1, 3})
        for value in ("999", "5-3", "0", ""):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.module.parse_pages(value, 5, None)
        with self.assertRaises(ValueError):
            self.module.parse_pages(None, 5, 0)

    def test_missing_paddle_dependencies_make_check_fail(self):
        with tempfile.TemporaryDirectory() as temporary, \
             mock.patch.object(self.module, "load_core_packages", return_value=["numpy"]), \
             mock.patch.object(self.module, "package_version", return_value=None), \
             redirect_stdout(StringIO()):
            result = self.module.main(["--check-tools", "--cache-dir", temporary])
        self.assertEqual(result, 2)

    def test_input_cannot_be_overwritten_in_place(self):
        with tempfile.TemporaryDirectory() as temporary, redirect_stderr(StringIO()):
            source = Path(temporary) / "source.pdf"
            source.write_bytes(b"placeholder")
            self.assertEqual(self.module.main([str(source), str(source)]), 2)


class PaddleExtractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["CASE_PDF_OCR_PADDLE_REEXEC"] = "1"
        cls.module = load_module("paddleocr_extract_test", "paddleocr_extract.py")

    def test_empty_directory_is_an_error(self):
        with tempfile.TemporaryDirectory() as temporary, \
             mock.patch.object(self.module, "print_status", return_value=True), \
             redirect_stderr(StringIO()):
            self.assertEqual(self.module.main([temporary]), 2)
            self.assertFalse((Path(temporary) / "OCR成果").exists())


class PackagingTests(unittest.TestCase):
    def test_skill_frontmatter_and_ui_prompt_match(self):
        skill = (ROOT / "chinese-lawyer-case-ocr-skill" / "SKILL.md").read_text(encoding="utf-8")
        ui = (ROOT / "chinese-lawyer-case-ocr-skill" / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertTrue(skill.startswith("---\nname: chinese-lawyer-case-ocr-skill\n"))
        self.assertIn("$chinese-lawyer-case-ocr-skill", ui)

    def test_public_skill_has_no_private_board_or_process_folder(self):
        skill = (ROOT / "chinese-lawyer-case-ocr-skill" / "SKILL.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn(".agents-shared", skill)
        self.assertNotIn("OCR过程文件", skill + readme)

    def test_installer_requires_explicit_target(self):
        help_result = subprocess.run(["bash", str(ROOT / "install.sh"), "--help"], text=True, capture_output=True)
        self.assertEqual(help_result.returncode, 0)
        self.assertIn("--target", help_result.stdout)


if __name__ == "__main__":
    unittest.main()
