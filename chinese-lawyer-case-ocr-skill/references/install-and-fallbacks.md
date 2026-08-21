# 参数与故障处理

## 路线

- 默认：`ocr_case_pdfs.py --profile balanced`。
- 大批量普通附件：`fast`，速度优先，不自动旋转或纠偏。
- 核心证据、较差扫描：`careful`。
- 个别顽固 PDF：`troubleshoot`。
- 旧文字层损坏：`--mode redo-ocr`；脚本会自动关闭与它冲突的图像处理参数。
- 必须整体栅格化重做：`--mode force-ocr`，可能降低图像质量，只在必要时使用。

四个档位默认都不设整本文件超时。`fast` 和 `troubleshoot` 设单页 30 秒上限；被跳过的低文本页必须通过质检报告发现。

## PaddleOCR

先让评估脚本打印建议页码：

```bash
python3 "$SKILL/scripts/assess_ocr_strategy.py" "<案卷文件夹>"
```

基础版要害页效果不足时，再对无旧文字层的原件做局部增强：

```bash
python3 "$SKILL/scripts/paddle_searchable_pdf.py" "原件.pdf" "OCR成果/原件_OCR.paddle.pdf" \
  --base-pdf "OCR成果/原件_OCR.pdf" --pages 3,7-9 --fail-if-selected-has-text
```

脚本拒绝输入输出同路径、拒绝静默覆盖已有文件，并原子写入新 PDF。验收新文件后再决定是否替换基础版；不得改动原件。

只需要文本和坐标时使用：

```bash
python3 "$SKILL/scripts/paddleocr_extract.py" "<案卷文件夹>"
```

结果仍写入 `OCR成果/`。模型缓存统一放在 `~/.case-pdf-ocr/`，不在案卷目录生成缓存文件夹。

## 失败处理

- 退出码 `0`：脚本完成，仍须读质检报告。
- 退出码 `1`：处理或质检存在失败项。
- 退出码 `2`：参数、输入或依赖不满足。
- 输出已存在时默认保留；只有确认需要重做才传 `--overwrite`。
- 空目录、损坏或加密 PDF、缺少中文语言包都不得算成功。

## 人工复核

低文本页、横页、表格、手写、身份证件、签章和印章必须看原图。OCR 文字不得用于推断或补齐看不清的姓名、案号、日期、金额。

检查 Markdown 中异常码位时，按 Unicode 码位判断 U+2E80–2EFF、U+2F00–2FDF、U+F900–FAFF、U+FE30–FE4F；不要用字面量汉字区间正则。
