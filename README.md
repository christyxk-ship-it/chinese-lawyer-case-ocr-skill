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
4. 输出质量报告、失败清单、文本副本和结构检查结果。

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
python3 scripts/assess_ocr_strategy.py "/path/to/PDF-or-folder"
python3 scripts/ocr_case_pdfs.py "/path/to/PDF-or-folder" --mode skip-text --profile fast --sanitize-input always --languages chi_sim+eng
```

如评估结果建议某些页使用 PaddleOCR：

```bash
python3 scripts/paddle_searchable_pdf.py "input.pdf" "PaddleOCR可搜索PDF/input_hybrid.pdf" --base-pdf "OCR可检索PDF/input_OCR.pdf" --pages "3,24,29-30" --profile balanced --dump-text "PaddleOCR转写/input_hybrid.txt"
```

## 输出

- `OCR评估/`：页级分流评估。
- `OCR可检索PDF/`：OCRmyPDF/Tesseract 基础可检索 PDF。
- `OCR文本/`：基础 OCR 文本副本。
- `OCR报告/`：manifest、失败清单、结构检查、质量报告。
- `PaddleOCR可搜索PDF/`：PaddleOCR 高质量或混合可搜索 PDF。
- `PaddleOCR转写/`：PaddleOCR 逐页转写文本。

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

尚未选择开源许可证。未添加许可证前，默认保留全部权利。
