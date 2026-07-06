# 安装与兜底方案

## 主路线

生产 OCR 优先使用 OCRmyPDF + Tesseract。目标是保留 PDF 外观，同时添加可检索文字层，最终交付可打开、可检索、结构检查通过的 PDF 副本。

必需命令行工具：

- `ocrmypdf`
- `tesseract`
- `gs`（Ghostscript）
- `qpdf`

常用检查命令：

```bash
which ocrmypdf
which tesseract
which gs
which qpdf
tesseract --list-langs
```

中文法律案件材料至少确认有：

- `chi_sim`
- `eng`

如可能出现繁体中文，再加 `chi_tra`。

## 工具缺失时

不要假装 OCR 成功。明确告诉用户缺少哪些工具，并提供以下路线之一：

1. 安装缺失的本地工具，然后重新跑批次。
2. 只用 `--mode scan-only` 生成清点结果。
3. 临时使用 macOS Vision 提取文本副本，并明确标注这不是可检索 PDF 输出，不能视为 OCR 完成。
4. 只有在已安装且用户偏好界面自动化时，才使用 Acrobat、ABBYY 等桌面 OCR 产品。

联网安装、包管理器安装、写入工作区以外目录，都需要用户批准。

## PaddleOCR 增强路线

主路线 OCRmyPDF 跑完后，对疑难材料使用 PaddleOCR，尤其是截图、复杂表格、印章、低质量扫描件，以及 Tesseract 提取文字异常偏少的文件。PaddleOCR 不替代 OCRmyPDF 生成可检索 PDF；它生成文本副本和 JSON/坐标副本，供审阅、提取和质量比对使用，不能单独作为最终 OCR 交付。

如果目标是更干净的可搜索 PDF，而不是只要文本/坐标，使用 `scripts/paddle_searchable_pdf.py`。该路线借鉴了逐行 bbox 叠加隐形文字层的做法，识别更干净，但速度慢、耗算力更高，只用于核心文件、疑难页或低质量输出的二次增强：

```bash
python3 scripts/paddle_searchable_pdf.py "input.pdf" "output_可搜索.pdf" --profile balanced --dump-text "output_转写.txt"
python3 scripts/paddle_searchable_pdf.py "input.pdf" "output_可搜索.pdf" --profile fast --pages 1-3,8
python3 scripts/paddle_searchable_pdf.py "input.pdf" "output_可搜索.pdf" --profile careful --lang chinese_cht
```

PaddleOCR 可搜索 PDF 档位：

- `--profile fast`：默认倍率较低，适合抽样页、质量复核和大文件局部增强。
- `--profile balanced`：默认建议档，适合重要 PDF 的完整增强。
- `--profile careful`：小字、表格密集或扫描质量差时使用；更慢。

节省算力原则：能只跑低文本页、表格页、核心证据页，就不要全文件跑；能用 `--profile fast` 判断质量，就不要直接上 `careful`；能用 OCRmyPDF 达标，就不要重复跑 PaddleOCR。

方向、水印或旧文字层处理原则：PaddleOCR 生成可搜索 PDF 时，选中页应来自视觉方向正确、无旧文字层的图片底稿。修复已有 OCR 成品时，先把需要重做的页输出到 `OCR过程文件/OCR输入PDF/`，再用 `--fail-if-selected-has-text` 防止把新文字层叠到旧文字层上。

本机当前环境：

```bash
/Users/xuqianchuan/Documents/Codex/tools/paddleocr/bin/python
/Users/xuqianchuan/Documents/Codex/tools/paddleocr/cache
```

2026-07-02 已验证安装版本：

- `paddleocr==3.7.0`
- `paddlepaddle==3.3.1`

常用检查：

```bash
python3 scripts/paddleocr_extract.py --check-tools
python3 scripts/paddleocr_extract.py "/path/to/case-folder" --max-files 1
```

PaddleOCR 脚本检测到 `/Users/xuqianchuan/Documents/Codex/tools/paddleocr/bin/python` 存在时，会自动用该 Python 重新执行自己。`paddle_searchable_pdf.py` 默认使用当前工作目录下的 `OCR过程文件/PaddleOCR缓存/`，并会复用已下载的 PP-OCRv6 检测/识别模型，避免在受限环境里写入不可写缓存目录。

简体中文 PaddleOCR 默认设置：

```bash
python3 scripts/paddleocr_extract.py "/path/to/case-folder" --lang ch --ocr-version PP-OCRv6
```

繁体中文：

```bash
python3 scripts/paddleocr_extract.py "/path/to/case-folder" --lang chinese_cht --ocr-version PP-OCRv6
```

如果第一次运行出现模型源或网络错误，说明 Python 包已安装，但模型权重尚未缓存。此时要么允许一次性联网下载，要么提供本地模型目录。模型缓存到 `tools/paddleocr/cache/official_models` 后，正常本地运行即可使用缓存模型。

## 推荐 OCRmyPDF 设置

默认/平衡：

```bash
ocrmypdf -l chi_sim+eng --skip-text --deskew --rotate-pages --jobs 2 --optimize 1 input.pdf output.pdf
```

怀疑已有文字层损坏时：

```bash
ocrmypdf -l chi_sim+eng --redo-ocr --deskew --rotate-pages --jobs 2 --optimize 1 input.pdf output.pdf
```

对顽固图片型扫描件，且用户可接受一定保真度取舍时：

```bash
ocrmypdf -l chi_sim+eng --force-ocr --deskew --rotate-pages --jobs 2 --optimize 1 input.pdf output.pdf
```

对大批量报告附件，且速度比自动旋转/纠偏更重要时：

```bash
ocrmypdf -l chi_sim+eng --skip-text --output-type pdf --jobs 4 --optimize 0 --tesseract-timeout 8 --tesseract-non-ocr-timeout 5 input.pdf output.pdf
```

对下载报告或网页抓取 PDF，如在元数据后处理阶段失败，先重建页面内容再 OCR：

```bash
qpdf --empty --pages input.pdf -- sanitized.pdf
ocrmypdf -l chi_sim+eng --skip-text --output-type pdf sanitized.pdf output.pdf
```

避免破坏性原地替换。始终先写入单独输出路径。

## 脚本档位

优先使用封装脚本档位，不要反复手写长 OCRmyPDF 命令：

- `--profile careful`：核心诉讼材料，保留纠偏/旋转和更干净输出。
- `--profile fast --sanitize-input always`：大批量报告/证据附件，减少坏元数据失败，使用更快的 PDF 输出。
- `--profile troubleshoot`：顽固 PDF，先清理输入，并允许更长单文件运行时间。

`careful` 档位只有在本机存在 `unpaper` 时才自动启用 `--clean-final`。如果缺少 `unpaper`，不要让 OCR 因清理步骤失败而中断；首要目标仍然是生成可检索 PDF。只有用户明确要求更强清理效果时，才考虑安装 `unpaper` 后重跑。

脚本每处理一个文件就写入 `ocr_manifest.csv`；默认跳过既有 `ok`/`exists` 记录；除非传入 `--no-sidecar-text`，否则创建 `OCR过程文件/OCR文本/` 文本副本；除非传入 `--no-pdf-check`，否则对 OCR 输出运行 `qpdf --check`；每次都会写入 `page_text_manifest.csv` 逐页文字量清单；最后写入 `OCR质量检查.md`。

完成判断以 `OCR成果：可检索PDF/` 中的可搜索 PDF 为准：文件必须存在、可打开、可检索，通过结构检查，并通过逐页文字层检查。文本副本、PaddleOCR 结果和报告只用于质检、检索辅助和疑难材料增强，统一归入 `OCR过程文件/`。

## 质量信号

以下情况视为需要抽查的警告：

- OCR 命令非零退出。
- 输出 PDF 缺失或明显小于预期。
- 输出 PDF 未通过 `qpdf --check`。
- OCR 后可提取文字数量接近零。
- `page_text_manifest.csv` 中某些正文页文字量异常偏低。
- 横向/旋转页只做了页面外观旋转，没有重建对应文字层。
- PaddleOCR 选中页已经存在旧文字层，容易形成新旧文字层叠加。
- 页数发生变化。
- 多页出现乱码标点或重复片段。
- 表格、手写内容、印章、身份证件或照片是重要证据。
- 文件加密、损坏或页面尺寸异常。
- OCRmyPDF 日志出现元数据 `UnicodeDecodeError`；用 `--sanitize-input always` 或 `--profile troubleshoot` 重跑。

对大型案件材料，先报告确切读取缺口，再用关键词、日期、人名、案号、金额和证据编号做定向提取。

## 速度、准确率与 token 策略

- 批量默认：OCRmyPDF/Tesseract。它最快、最省算力，适合先把整批案卷变成可检索 PDF。
- 质量增强：PaddleOCR 可搜索 PDF。只对核心证据、疑难页、Tesseract 低文本/乱码文件使用。
- 抽样优先：先用 `scan-only`、清单、关键词和少量页测试判断质量，再决定是否全文件增强。
- 少读文本：不要把 OCR 全文塞进对话。产出文本副本后，用 `rg`、页码、关键词、金额、人名、案号做定向检索。
- 少重跑：尊重 manifest 和已存在输出；除非参数或质量目标改变，不要 `--overwrite`。
