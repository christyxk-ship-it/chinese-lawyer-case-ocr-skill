# 发布说明

## v0.3.1

- 方向陷阱修正（Intel Mac 实战反馈）：明确"以阅读器显示方向为准"的底稿规则——显示正立的页（含靠 /Rotate 标记正立的）直接 gs 栅格化，禁止再 `qpdf --rotate`，否则成果整体转倒；SKILL.md 与 references 已写清判断标准。
- Intel Mac 兼容：paddlepaddle 3.1+ 无 Intel 轮子、3.0.0 静态引擎与 PP-OCRv6 模型不兼容（strides 报错）——`paddle_searchable_pdf.py` 现内置静态→动态引擎自动回退；依赖清单加入 safetensors。
- Python 版本说明放宽：3.9 实测可跑通全部依赖，推荐 3.10+；INSTALL.md 同步更新。
- 安装说明补齐"没有 Homebrew 时的人机分工"与 Python 补救路径（干净 Mac 实战反馈）。

## v0.3.0

- 面向分发的去个人化改造：依赖环境改为自动探测（`CASE_OCR_PYTHON` / `CASE_OCR_PADDLE_ROOT` 环境变量 > `~/.case-pdf-ocr/` 标准安装位置 > 既有位置兜底），脚本内不再含任何个人路径；依赖缺失时给出明确安装指引。
- 新增 `README.md`（面向使用者）、`INSTALL.md`（面向执行安装的 AI 助手）、`install.sh`（一键安装），支持"下载后对 AI 说一句话"完成安装。
- 输出结构重构：成果目录改为 `OCR成果/`，每个原件产出 `_OCR.pdf` + 同名 `_OCR.md` 文本副本；过程目录合并为 `报告/底稿/转写/缓存` 四类。
- 文字层可移植性修复：隐形文字层改用嵌入式中文字体并自动生成 ToUnicode 映射，Poppler/Ghostscript 等标准提取器均可读；验收流程增加 gs txtwrite 第二提取器抽查。
- 模型缓存全局复用：默认直接使用 PaddleOCR 环境下的全局缓存，不再逐案卷复制模型。
- manifest 跨批次合并写回，分批处理不再丢失历史记录。
- 评估产物 `*.paddle_pages.txt` 直接串接 `--pages`；补全 qpdf+gs 生成"方向正确、无旧文字层底稿"的标准命令。

## v0.2.1

- 增加 `tools/sync_from_local_skill.py`，用于把本机 `~/.codex/skills/case-pdf-ocr` 自动同步到公开发布包。
- 同步脚本保留公开版 skill 机器名 `chinese-lawyer-case-ocr-skill`，避免直接覆盖成私有本地名。
- 同步前后执行脚本语法检查和 skill 校验；可选 `--commit --push` 自动提交并推送。
- `.gitignore` 增加新版 OCR 成果/过程目录，防止测试产物进入公开仓库。

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
