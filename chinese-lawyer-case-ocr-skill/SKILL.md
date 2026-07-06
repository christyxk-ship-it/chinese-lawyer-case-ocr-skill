---
name: chinese-lawyer-case-ocr-skill
description: "中文执业律师案卷 OCR skill。批量 OCR 并质检中文法律案件 PDF，首要交付可打开、可检索、结构检查通过的 PDF 副本。用于把扫描件或图片型案卷材料转成可检索 PDF，并在速度、准确率、算力/token 之间先评估再分流：OCRmyPDF/Tesseract 负责批量基础 OCR，PaddleOCR 负责核心、疑难、表格、低质页面的高质量增强。"
---

# 案件 PDF OCR

## 一句话原则

目标是 **可检索 PDF**，不是单纯 TXT、JSON 或截图转写。默认最终只保留一份可搜索 PDF，放入 `OCR成果：可检索PDF/`；除最终成果外，评估、报告、文本、缓存、转写、备份和中间件都放入 `OCR过程文件/`。先用快、省资源的 OCRmyPDF/Tesseract 批量跑，再把 PaddleOCR 留给真正需要更干净文字层的页面，若生成增强版，以增强版作为最终件。

## 跨 Agent 使用

这个目录是 Codex skill，workbuddy 不能自动加载 `~/.codex/skills` 的触发机制。但本 skill 的脚本都是普通本地 Python；workbuddy、Claude、Hermes 可以通过任务包调用这些脚本，或把脚本/说明复制到 `.agents-shared/` 后按同一流程使用。跨 agent 状态仍写 `.agents-shared/state/board.yaml`。

## 标准流程

1. 先评估分流：

```bash
python3 scripts/assess_ocr_strategy.py "/path/to/PDF-or-folder" --output-dir "OCR过程文件/OCR评估"
```

产物在 `OCR过程文件/OCR评估/`：`ocr_strategy.md`、`ocr_strategy.csv`、`*.paddle_pages.txt`、`*.ocrmypdf_pages.txt`。

2. 并行跑基础 OCR 与高质量页 OCR。横向、旋转、水印页先生成视觉方向正确、无旧文字层的 `OCR过程文件/OCR输入PDF/` 底稿，再交给 PaddleOCR；不要在旧 OCR 成品上直接补叠文字层：

```bash
python3 scripts/ocr_case_pdfs.py "/path/to/PDF-or-folder" --mode skip-text --profile fast --sanitize-input always --languages chi_sim+eng --output-dir "OCR成果：可检索PDF" --report-dir "OCR过程文件/OCR报告" --text-dir "OCR过程文件/OCR文本"
python3 scripts/paddle_searchable_pdf.py "OCR过程文件/OCR输入PDF/input_方向水印处理后.pdf" "OCR成果：可检索PDF/input_paddle.pdf" --pages "评估出的页码" --profile balanced --fail-if-selected-has-text --dump-text "OCR过程文件/PaddleOCR转写/input.txt" --cache-dir "OCR过程文件/PaddleOCR缓存"
```

核心证据或正式交付件，把 `fast` 换成 `careful` 或 `balanced`。繁体材料加 `chi_tra` 或 PaddleOCR `--lang chinese_cht`。

3. 如需混合成品：先等 OCRmyPDF 基础版完成，再让 PaddleOCR 覆盖评估出的疑难页；混合成品通过验收后，只保留这一份作为最终可搜索 PDF，基础 OCR PDF 作为中间件清理或不作为交付件列示：

```bash
python3 scripts/paddle_searchable_pdf.py "OCR过程文件/OCR输入PDF/input_方向水印处理后.pdf" "OCR成果：可检索PDF/input_hybrid.pdf" --base-pdf "OCR成果：可检索PDF/input_OCR.pdf" --pages "评估出的页码" --profile balanced --fail-if-selected-has-text --dump-text "OCR过程文件/PaddleOCR转写/input_hybrid.txt" --cache-dir "OCR过程文件/PaddleOCR缓存"
```

4. 验收后再进入法律审查：

```bash
qpdf --check "output.pdf"
python3 scripts/ocr_case_pdfs.py "output.pdf" --mode scan-only --report-dir "OCR过程文件/OCR报告/最终检查"
```

检查页数是否一致、PDF 是否可打开、关键词是否能命中、`page_text_manifest.csv` 逐页文字量是否异常、低文本页是否需要人工复核。

## 防止方向/文字层错位

- 横向或旋转页先修视觉方向，再 OCR；不要只旋转最终 PDF 的页面外观。
- 去水印、裁边、方向调整后，要从无旧文字层的底稿重新生成文字层；不要在已有 OCR 成品上继续叠加。
- PaddleOCR 覆盖疑难页时加 `--fail-if-selected-has-text`，如果选中页已有文字层，先回到 `OCR过程文件/OCR输入PDF/` 的图片底稿。
- 最终验收必须看 `OCR过程文件/OCR报告/最终检查/page_text_manifest.csv`，逐页核对后几页、横页、签章页和附件页；不能只看抽样总字数。
- 签字盖章页、残章页可以文字少，但要在报告中说明“页面内容本身少”，不能默认为识别成功。

## 分流规则

- 已有文字层：交给 OCRmyPDF `skip-text` 保留，不重复 OCR。
- 普通扫描页：OCRmyPDF/Tesseract，速度快、算力低，适合批量。
- 核心证据、表格密集、横向/旋转、截图、印章、低文本或乱码页：PaddleOCR 可搜索 PDF。
- 只要文本/坐标，不需要重做可搜索 PDF：用 `scripts/paddleocr_extract.py`。

## 输出约定

- 最终交付默认只保留一份可搜索 PDF，统一放在 `OCR成果：可检索PDF/`。仅跑 OCRmyPDF 时，放基础可检索 PDF；若跑 PaddleOCR 高质量或混合增强，则用增强件替换或覆盖为最终件，并清理同源基础 OCR PDF。
- `OCR成果：可检索PDF/`：唯一最终可搜索 PDF 成果目录；不要再另建 `OCR可检索PDF/`、`PaddleOCR可搜索PDF/` 等并列成品目录。
- `OCR过程文件/`：除最终成果 PDF 外的全部 OCR 过程文件根目录。
- `OCR过程文件/OCR文本/`：基础 OCR 文本副本。
- `OCR过程文件/OCR报告/`：manifest、失败清单、结构检查、质量报告。
- `OCR过程文件/OCR评估/`：页级分流评估。
- `OCR过程文件/OCR输入PDF/`：OCR 前的输入副本或归集版本。
- `OCR过程文件/PaddleOCR缓存/`：PaddleOCR 模型、临时文件和运行缓存。
- `OCR过程文件/PaddleOCR转写/`：逐页转写文本，供核对；不要整份贴进对话。
- `OCR过程文件/PaddleOCR文本/`、`OCR过程文件/PaddleOCR结构/`、`OCR过程文件/PaddleOCR报告/`：仅转写/结构化提取时的文本、JSON 和报告。
- `OCR过程文件/水印与OCR修正备份/`、`OCR过程文件/页面方向调整备份/`、`OCR过程文件/去水印底稿/`：方向、水印、重 OCR 等修正过程的底稿和备份。
- 不在案件根目录保留 `OCR可检索PDF/`、`PaddleOCR可搜索PDF/`、`PaddleOCR缓存/` 等 OCR 并列目录；如旧流程生成，整理时移入 `OCR过程文件/` 或并入 `OCR成果：可检索PDF/`。

## 省算力与省 token

- 先评估，再跑；先抽样，再全量。
- 能用 OCRmyPDF 达标，就不跑 PaddleOCR。
- PaddleOCR 优先跑页码范围，不默认全文件。
- 同一原件默认只保留一份最终可搜索 PDF，统一进入 `OCR成果：可检索PDF/`；其他过程文件统一归入 `OCR过程文件/`，避免基础 OCR 与增强 OCR 并列造成版本歧义。
- 尊重 manifest 和已存在输出，不随意 `--overwrite`。
- 法律分析用 `rg`、页码、关键词、人名、案号、金额定向检索，不把 OCR 全文塞进聊天。

## 依赖与兜底

依赖缺失、PaddleOCR 缓存、OCRmyPDF 参数、故障排查见 `references/install-and-fallbacks.md`。未经用户明确授权，不上传法律 PDF 到云端 OCR。
