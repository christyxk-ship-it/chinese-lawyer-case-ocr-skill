# 发布说明

## v0.2.0

- 默认成果/过程分层：最终可搜索 PDF 统一进入 `OCR成果：可检索PDF/`，其余 OCR 评估、报告、文本、缓存、转写和中间底稿统一进入 `OCR过程文件/`。
- 增加方向/旧文字层防线：横向、旋转、水印页先生成无旧文字层输入底稿，再重建文字层；PaddleOCR 可用 `--fail-if-selected-has-text` 阻止叠加旧文字层。
- 增加逐页文字层质检：`ocr_case_pdfs.py` 默认输出 `page_text_manifest.csv`，列出每页文字量、方向、尺寸和样本文字。
- 根目录批量处理时默认跳过 `OCR成果：可检索PDF/` 和 `OCR过程文件/`，避免把成果或过程备份再次纳入 OCR。
- README 和 skill 使用示例更新为成果/过程目录结构。

## v0.1.0

- 初始发布包。
- 支持页级 OCR 分流评估。
- 支持 OCRmyPDF/Tesseract 批量生成可检索 PDF。
- 支持 PaddleOCR 对核心/疑难页面生成高质量可搜索 PDF。
- 支持混合输出：基础页沿用 OCRmyPDF，疑难页用 PaddleOCR 覆盖。
- 输出质量报告、结构检查、文本副本和失败清单。
