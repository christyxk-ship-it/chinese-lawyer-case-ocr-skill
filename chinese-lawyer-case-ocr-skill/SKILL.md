---
name: chinese-lawyer-case-ocr-skill
description: "在本地把扫描件/图片型中文法律案卷 PDF 转成可检索 PDF 并质检。当用户要求 OCR 案卷、让判决书等扫描 PDF 可搜索/可复制文字、给 PDF 加文字层，或提供的 PDF 无法选中文字时使用。"
---

# 案件 PDF OCR

## 原则

目标是可检索 PDF。先用省算力的 OCRmyPDF/Tesseract 批量打底，PaddleOCR 只增强评估出的疑难页。未经用户明确授权，不上传法律 PDF 到云端。

所有命令先 `cd` 到案卷根目录再执行（脚本默认输出目录随输入路径解析），脚本用绝对路径引用，`SKILL` 设为本 SKILL.md 所在目录：

```bash
SKILL=<本 skill 安装目录>   # 即本文件所在目录，如 ~/.workbuddy/skills/chinese-lawyer-case-ocr-skill
```

## 标准流程

1. 评估分流：

```bash
python3 "$SKILL/scripts/assess_ocr_strategy.py" .
```

产物在 `OCR过程文件/报告/`：`ocr_strategy.md/.csv`，以及每件的 `<名>.paddle_pages.txt` / `<名>.ocrmypdf_pages.txt` 页码范围。

2. 基础 OCR（批量）：

```bash
python3 "$SKILL/scripts/ocr_case_pdfs.py" . --mode skip-text --profile fast --sanitize-input always
```

注意：`fast` 档不做自动旋转/纠偏。核心证据或正式交付件改用 `careful` 或 `balanced`；繁体材料 `--languages` 加 `chi_tra`。

3. 疑难页增强（评估出 paddle 页时）。先生成方向正确、无旧文字层的底稿，再叠加，验收后替换基础版：

```bash
qpdf "input.pdf" --rotate=+90:3,7 -- "OCR过程文件/底稿/input_旋转.pdf"        # 如需修方向（示例：第3、7页转90°）
gs -o "OCR过程文件/底稿/input_底稿.pdf" -sDEVICE=pdfimage24 -r300 "OCR过程文件/底稿/input_旋转.pdf"   # 栅格化：固化方向并剥掉旧文字层
python3 "$SKILL/scripts/paddle_searchable_pdf.py" "OCR过程文件/底稿/input_底稿.pdf" "OCR成果/input_OCR.new.pdf" \
  --base-pdf "OCR成果/input_OCR.pdf" --pages "$(cat 'OCR过程文件/报告/input.paddle_pages.txt')" \
  --fail-if-selected-has-text --dump-text "OCR过程文件/转写/input.txt"
gs -q -dNOPAUSE -dBATCH -sDEVICE=txtwrite -sOutputFile=- "OCR成果/input_OCR.new.pdf" | head -20   # 第二提取器抽查：必须能读出中文，防止文字层只对部分阅读器可见
mv "OCR成果/input_OCR.new.pdf" "OCR成果/input_OCR.pdf"                        # 验收通过后替换，只留一份
```

4. 验收：重跑第 2 步命令即可——manifest 断点续跑不会重复 OCR，只从最终 PDF 刷新 md 副本、逐页文字量清单和结构检查。然后核对 `OCR过程文件/报告/` 下的 `OCR质量检查.md` 与 `page_text_manifest.csv`：页数一致、逐页文字量无异常，后几页、横页、签章页逐页核对。签章页文字少要在报告说明"页面内容本身少"，不能默认为识别成功。

## 分流规则

- 已有文字层：`skip-text` 保留，不重复 OCR。
- 普通扫描页：OCRmyPDF/Tesseract，批量、省算力。
- 核心证据、表格密集、横向/旋转、印章、低文本或乱码页：PaddleOCR（必须先做底稿）。
- 只要文本/坐标、不需要可搜索 PDF：`scripts/paddleocr_extract.py`。

## 防止方向/文字层错位

- 旋转/横向/水印页：先按第 3 步 qpdf+gs 生成底稿再 OCR；禁止在旧 OCR 成品上直接叠文字层，`--fail-if-selected-has-text` 兜底。
- `--profile fast` 不做自动旋转：旋转页必须走 Paddle 底稿路线，或改用 balanced/careful。

## 输出约定

- `OCR成果/`：每个原件恰好两个文件——`<原名>_OCR.pdf`（唯一最终可检索 PDF，增强版验收后替换基础版）和 `<原名>_OCR.md`（逐页文本副本，供检索与引用）。
- `OCR过程文件/`：`报告/`（评估、manifest、质检、日志）、`底稿/`（无文字层输入与修正备份）、`转写/`（PaddleOCR 转写与 JSON 结构）、`缓存/`（仅源缓存不可用时使用）。
- 旧流程生成的其他 OCR 目录，整理时并入上述结构。

## 省算力与省 token

- 先评估再跑，先抽样再全量；OCRmyPDF 达标就不上 PaddleOCR；PaddleOCR 只跑评估页码。
- 尊重 manifest 和已有输出，不随意 `--overwrite`。
- 法律分析用 `rg` 在 `OCR成果/*.md` 定向检索（关键词、人名、案号、金额），不把全文塞进对话。

## 跨 Agent 使用

脚本是普通本地 Python，其他 agent（workbuddy、Claude、Hermes）可按同一流程直接调用；跨 agent 状态写 `.agents-shared/state/board.yaml`。

## 依赖与兜底

安装检查、PaddleOCR 缓存、OCRmyPDF 参数细节、故障排查见 `references/install-and-fallbacks.md`。
