---
name: chinese-lawyer-case-ocr-skill
description: "在本地把扫描件或图片型中文法律案卷 PDF 转成可检索 PDF，并生成逐页文本和质检报告。用于 PDF 无法搜索、复制文字或需要批量添加文字层的场景。"
---

# 中文法律案卷 OCR

目标：不改原件、不上传文件，只在案卷目录生成一个 `OCR成果/`。

## 标准处理

1. 先确认用户允许在本机安装依赖；任何案卷上传云端都须另行明确授权。
2. 将 `SKILL` 指向本目录，运行：

```bash
python3 "$SKILL/scripts/ocr_case_pdfs.py" "<案卷文件夹>" --profile balanced
```

批量附件可用 `fast`；核心证据或质量较差的扫描件用 `careful`。只有明确要推倒旧文字层时才用 `--mode redo-ocr` 或 `force-ocr`。

3. 只有命令退出码为 0，且 `OCR成果/OCR质检报告.md` 没有失败项，才可报告技术处理完成。
4. 核对每份 PDF 页数、可搜索性和低文本页面；姓名、案号、日期、金额、手写、表格、签章及印章必须对照原图人工复核。

## 输出

`OCR成果/` 是唯一保留目录：

- `<原名>_OCR.pdf`：可搜索 PDF。
- `<原名>_OCR.md`：按页提取的文本。
- `OCR质检报告.md`：失败项和低文本页。

中间 PDF、缓存和日志只使用系统临时目录或 `~/.case-pdf-ocr/` 的全局依赖缓存，不在案卷目录保留过程文件夹。

## PaddleOCR 增强

基础版在要害页效果不足时，先运行 `assess_ocr_strategy.py`；它默认只在终端打印建议，不写过程文件。再只对必要页使用 `paddle_searchable_pdf.py`。该脚本要求新输出路径，拒绝直接覆盖原件或已有成果。

PaddleOCR 只是另一种 OCR，也会错字、漏字；不能依据上下文补造文字。具体参数和异常处理见 [references/install-and-fallbacks.md](references/install-and-fallbacks.md)。
