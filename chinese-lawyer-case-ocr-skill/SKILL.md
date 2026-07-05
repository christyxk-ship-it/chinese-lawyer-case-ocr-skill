---
name: chinese-lawyer-case-ocr-skill
description: "中文执业律师案卷 OCR skill。批量 OCR 并质检中文法律案件 PDF，首要交付可打开、可检索、结构检查通过的 PDF 副本。用于把扫描件或图片型案卷材料转成可检索 PDF，并在速度、准确率、算力/token 之间先评估再分流：OCRmyPDF/Tesseract 负责批量基础 OCR，PaddleOCR 负责核心、疑难、表格、低质页面的高质量增强。"
---

# 案件 PDF OCR

## 一句话原则

目标是 **可检索 PDF**，不是单纯 TXT、JSON 或截图转写。默认先用快、省资源的 OCRmyPDF/Tesseract 批量跑，再把 PaddleOCR 留给真正需要更干净文字层的页面。

## 跨 Agent 使用

这个目录是 Codex skill，workbuddy 不能自动加载 `~/.codex/skills` 的触发机制。但本 skill 的脚本都是普通本地 Python；workbuddy、Claude、Hermes 可以通过任务包调用这些脚本，或把脚本/说明复制到 `.agents-shared/` 后按同一流程使用。跨 agent 状态仍写 `.agents-shared/state/board.yaml`。

## 标准流程

1. 先评估分流：

```bash
python3 scripts/assess_ocr_strategy.py "/path/to/PDF-or-folder"
```

产物在 `OCR评估/`：`ocr_strategy.md`、`ocr_strategy.csv`、`*.paddle_pages.txt`、`*.ocrmypdf_pages.txt`。

2. 并行跑基础 OCR 与高质量页 OCR：

```bash
python3 scripts/ocr_case_pdfs.py "/path/to/PDF-or-folder" --mode skip-text --profile fast --sanitize-input always --languages chi_sim+eng
python3 scripts/paddle_searchable_pdf.py "input.pdf" "PaddleOCR可搜索PDF/input_paddle.pdf" --pages "评估出的页码" --profile fast --dump-text "PaddleOCR转写/input.txt"
```

核心证据或正式交付件，把 `fast` 换成 `careful` 或 `balanced`。繁体材料加 `chi_tra` 或 PaddleOCR `--lang chinese_cht`。

3. 如需混合成品：先等 OCRmyPDF 基础版完成，再让 PaddleOCR 覆盖评估出的疑难页：

```bash
python3 scripts/paddle_searchable_pdf.py "input.pdf" "PaddleOCR可搜索PDF/input_hybrid.pdf" --base-pdf "OCR可检索PDF/input_OCR.pdf" --pages "评估出的页码" --profile balanced --dump-text "PaddleOCR转写/input_hybrid.txt"
```

4. 验收后再进入法律审查：

```bash
qpdf --check "output.pdf"
python3 scripts/ocr_case_pdfs.py "output.pdf" --mode scan-only
```

检查页数是否一致、PDF 是否可打开、关键词是否能命中、低文本页是否需要人工复核。

## 分流规则

- 已有文字层：交给 OCRmyPDF `skip-text` 保留，不重复 OCR。
- 普通扫描页：OCRmyPDF/Tesseract，速度快、算力低，适合批量。
- 核心证据、表格密集、横向/旋转、截图、印章、低文本或乱码页：PaddleOCR 可搜索 PDF。
- 只要文本/坐标，不需要重做可搜索 PDF：用 `scripts/paddleocr_extract.py`。

## 输出约定

- `OCR可检索PDF/`：OCRmyPDF/Tesseract 基础可检索 PDF。
- `OCR文本/`：基础 OCR 文本副本。
- `OCR报告/`：manifest、失败清单、结构检查、质量报告。
- `OCR评估/`：页级分流评估。
- `PaddleOCR可搜索PDF/`：PaddleOCR 高质量或混合可搜索 PDF。
- `PaddleOCR转写/`：逐页转写文本，供核对；不要整份贴进对话。

## 省算力与省 token

- 先评估，再跑；先抽样，再全量。
- 能用 OCRmyPDF 达标，就不跑 PaddleOCR。
- PaddleOCR 优先跑页码范围，不默认全文件。
- 尊重 manifest 和已存在输出，不随意 `--overwrite`。
- 法律分析用 `rg`、页码、关键词、人名、案号、金额定向检索，不把 OCR 全文塞进聊天。

## 依赖与兜底

依赖缺失、PaddleOCR 缓存、OCRmyPDF 参数、故障排查见 `references/install-and-fallbacks.md`。未经用户明确授权，不上传法律 PDF 到云端 OCR。
