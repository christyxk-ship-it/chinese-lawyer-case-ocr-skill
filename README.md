# 中文执业律师案卷OCR-SKILL

面向中文执业律师案卷材料的本地 OCR skill。目标不是“转出一堆文本”，而是把扫描件、图片型 PDF、病历材料、证据附件等转成 **可打开、可检索、结构检查通过的 PDF**。

## 适用场景

- 中文诉讼案卷、仲裁案卷、证据附件批量 OCR。
- 扫描 PDF、图片型 PDF、病历/诊断证明/发票/合同扫描件。
- 需要在速度、准确率、算力之间做分层处理：普通页快速 OCR，疑难页高质量增强。

## Skill 名称

- GitHub 展示名：`中文执业律师案卷OCR-SKILL`
- Codex skill 机器名：`chinese-lawyer-case-ocr-skill`

Codex skill 的 `name` 字段必须使用小写英文、数字和短横线，所以机器名不能直接写中文。

## 核心流程

1. 先做页级评估，判断哪些页适合 OCRmyPDF，哪些页适合 PaddleOCR。
2. OCRmyPDF/Tesseract 批量生成基础可检索 PDF。
3. PaddleOCR 只处理核心、疑难、表格密集或低质量页面。
4. 横向、旋转、去水印页面先生成视觉方向正确且无旧文字层的输入底稿，再重建文字层。
5. 输出质量报告、失败清单、文本副本、结构检查结果和逐页文字层清单。

## 目录

```text
chinese-lawyer-case-ocr-skill/
├── SKILL.md
├── agents/openai.yaml
├── references/install-and-fallbacks.md
└── scripts/
    ├── assess_ocr_strategy.py
    ├── ocr_case_pdfs.py
    ├── paddle_searchable_pdf.py
    └── paddleocr_extract.py
```

## 快速使用

进入 skill 目录后：

```bash
python3 scripts/assess_ocr_strategy.py "/path/to/PDF-or-folder" --output-dir "OCR过程文件/OCR评估"
python3 scripts/ocr_case_pdfs.py "/path/to/PDF-or-folder" --mode skip-text --profile fast --sanitize-input always --languages chi_sim+eng --output-dir "OCR成果：可检索PDF" --report-dir "OCR过程文件/OCR报告" --text-dir "OCR过程文件/OCR文本"
```

如评估结果建议某些页使用 PaddleOCR：

```bash
python3 scripts/paddle_searchable_pdf.py "OCR过程文件/OCR输入PDF/input_方向水印处理后.pdf" "OCR成果：可检索PDF/input_hybrid.pdf" --base-pdf "OCR成果：可检索PDF/input_OCR.pdf" --pages "3,24,29-30" --profile balanced --fail-if-selected-has-text --dump-text "OCR过程文件/PaddleOCR转写/input_hybrid.txt" --cache-dir "OCR过程文件/PaddleOCR缓存"
```

## 输出

- `OCR成果：可检索PDF/`：唯一最终可搜索 PDF 成果目录。
- `OCR过程文件/`：除最终成果 PDF 外的全部 OCR 过程文件根目录。
- `OCR过程文件/OCR评估/`：页级分流评估。
- `OCR过程文件/OCR文本/`：基础 OCR 文本副本。
- `OCR过程文件/OCR报告/`：manifest、失败清单、结构检查、质量报告和 `page_text_manifest.csv`。
- `OCR过程文件/OCR输入PDF/`：OCR 前的输入副本或方向/水印处理后的底稿。
- `OCR过程文件/PaddleOCR缓存/`：PaddleOCR 模型、临时文件和运行缓存。
- `OCR过程文件/PaddleOCR转写/`：PaddleOCR 逐页转写文本。

## 质量防线

- 最终可搜索 PDF 只保留一份，避免基础 OCR 和增强 OCR 并列造成版本歧义。
- 方向调整、裁边、去水印后，必须从无旧文字层底稿重建文字层。
- PaddleOCR 覆盖疑难页时使用 `--fail-if-selected-has-text`，防止新旧文字层叠加。
- 最终验收查看 `OCR过程文件/OCR报告/最终检查/page_text_manifest.csv`，逐页核对后几页、横页、签章页和附件页。

## 维护同步

本机源 skill 位于 `~/.codex/skills/case-pdf-ocr`。公开仓库使用英文机器名 `chinese-lawyer-case-ocr-skill`，因此不要直接整目录覆盖。用仓库脚本同步：

```bash
python3 tools/sync_from_local_skill.py
python3 tools/sync_from_local_skill.py --commit --push
```

脚本会复制 `SKILL.md` 正文、`scripts/`、`references/`，保留公开版 frontmatter 和 `agents/openai.yaml`，然后运行语法检查与 skill 校验。只有校验通过且存在真实差异时，才会提交和推送。

## 依赖

主路线依赖：

- OCRmyPDF
- Tesseract，含 `chi_sim`、`eng`，必要时加 `chi_tra`
- Ghostscript
- qpdf

高质量增强路线依赖：

- PaddleOCR
- PaddlePaddle
- pypdfium2
- pypdf
- reportlab
- numpy

详细安装、兜底和故障处理见 `chinese-lawyer-case-ocr-skill/references/install-and-fallbacks.md`。

## 隐私边界

默认全部本地运行。未经律师或材料所有人明确授权，不上传法律 PDF、病历、证据材料到云端 OCR 服务。

## License

MIT License. 详见 `LICENSE`。
