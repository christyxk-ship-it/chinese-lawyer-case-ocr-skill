"""OCR 产物回归测试。

CI 只能证明代码没写错，证明不了识别结果没变——依赖升级（例如 pypdf、pypdfium2）
可能让文字层悄悄劣化而所有语法检查照样通过。本测试拿一份固定样本跑完整 OCR，
把结果和录好的基线比对，用来拦住这类静默劣化。

没装 OCR 工具的机器会跳过本测试，不影响其余测试。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SAMPLE = FIXTURES / "sample_judgment.pdf"
BASELINE = FIXTURES / "ocr_baseline.json"

REQUIRED_TOOLS = ("ocrmypdf", "tesseract", "gs")


def missing_tools() -> list[str]:
    return [name for name in REQUIRED_TOOLS if not shutil.which(name)]


def tesseract_has_chi_sim() -> bool:
    try:
        result = subprocess.run(
            ["tesseract", "--list-langs"], text=True, capture_output=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return "chi_sim" in result.stdout


def flatten(text: str) -> str:
    return "".join(text.split())


class OcrRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        absent = missing_tools()
        if absent:
            raise unittest.SkipTest(f"缺少 OCR 工具：{'、'.join(absent)}")
        if not tesseract_has_chi_sim():
            raise unittest.SkipTest("tesseract 缺少 chi_sim 语言包")
        try:
            from pypdf import PdfReader  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("缺少 pypdf")
        cls.baseline = json.loads(BASELINE.read_text(encoding="utf-8"))

    def test_sample_is_an_image_only_pdf(self):
        """样本必须没有原生文字层，否则测的就不是 OCR 了。"""
        from pypdf import PdfReader

        reader = PdfReader(str(SAMPLE))
        self.assertEqual(len(reader.pages), self.baseline["pages"])
        self.assertEqual(flatten(reader.pages[0].extract_text() or ""), "")

    def test_ocr_output_matches_baseline(self):
        from pypdf import PdfReader

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "result.pdf"
            completed = subprocess.run(
                [
                    "ocrmypdf", "-l", "chi_sim+eng", "--skip-text",
                    "--rotate-pages", "--optimize", "1",
                    str(SAMPLE), str(output),
                ],
                text=True, capture_output=True, timeout=600,
            )
            self.assertEqual(
                completed.returncode, 0,
                f"ocrmypdf 失败：\n{completed.stderr[-2000:]}",
            )
            reader = PdfReader(str(output))
            self.assertEqual(len(reader.pages), self.baseline["pages"])
            text = flatten("".join(page.extract_text() or "" for page in reader.pages))

        absent = [k for k in self.baseline["required_keywords"] if k not in text]
        self.assertEqual(
            absent, [],
            "文字层丢失基线关键词，识别质量已劣化。\n"
            f"  缺失：{absent}\n  实测文本：{text}",
        )

        expected = self.baseline["text_length"]
        tolerance = self.baseline["text_length_tolerance"]
        low, high = expected * (1 - tolerance), expected * (1 + tolerance)
        self.assertTrue(
            low <= len(text) <= high,
            "文字层字符数超出基线容差，可能是依赖升级导致的静默变化。\n"
            f"  基线 {expected}（允许 {low:.0f}–{high:.0f}），实测 {len(text)}\n"
            f"  实测文本：{text}",
        )


if __name__ == "__main__":
    unittest.main()
