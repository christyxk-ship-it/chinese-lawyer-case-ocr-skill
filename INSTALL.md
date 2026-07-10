# 安装说明（本文写给执行安装的 AI 助手）

你是用户的 AI 助手（WorkBuddy / Codex / Claude Code 等）。请按以下步骤把本技能包安装到用户机器上。目标平台为 macOS。每一步先自检再继续，失败时把错误原样告诉用户并按"故障排查"处理，不要假装成功。

## 0. 前提检查

```bash
uname -s          # 期望 Darwin
which brew        # 无输出则需先安装 Homebrew（第 1 步）
python3 --version # 期望 3.10+
```

## 1. 命令行工具（OCR 主引擎）

```bash
brew install ocrmypdf qpdf ghostscript tesseract tesseract-lang
```

- 没有 Homebrew 时，先征得用户同意再安装：https://brew.sh 官方脚本。
- 自检（三项都必须通过）：

```bash
which ocrmypdf qpdf gs tesseract        # 四个都要有路径
tesseract --list-langs | grep chi_sim   # 必须包含 chi_sim
ocrmypdf --version
```

## 2. 基础 Python 环境

```bash
python3 -m venv ~/.case-pdf-ocr/venv
~/.case-pdf-ocr/venv/bin/pip install --upgrade pip
~/.case-pdf-ocr/venv/bin/pip install numpy pypdf pypdfium2 pillow reportlab
```

## 3. PaddleOCR 环境（高精度增强引擎）

体积较大（约 1–2 GB），下载需要几分钟，请提前告知用户。

```bash
python3 -m venv ~/.case-pdf-ocr/paddle
~/.case-pdf-ocr/paddle/bin/pip install --upgrade pip
~/.case-pdf-ocr/paddle/bin/pip install paddlepaddle paddleocr numpy pypdf pypdfium2 pillow reportlab
```

OCR 模型会在首次实际运行时自动下载到 `~/.case-pdf-ocr/paddle/cache/`（全局缓存，只下载一次）。

## 4. 安装 skill 本体

把本仓库中的 `chinese-lawyer-case-ocr-skill/` 目录复制到你（AI 助手）的技能目录：

| 宿主 | 目标路径 |
|---|---|
| WorkBuddy | `~/.workbuddy/skills/chinese-lawyer-case-ocr-skill` |
| Codex | `~/.codex/skills/chinese-lawyer-case-ocr-skill` |
| Claude Code | `~/.claude/skills/chinese-lawyer-case-ocr-skill` |

```bash
cp -R <解压目录>/chinese-lawyer-case-ocr-skill ~/.workbuddy/skills/   # 按宿主替换目标
```

## 5. 自检

```bash
SKILL=~/.workbuddy/skills/chinese-lawyer-case-ocr-skill   # 按实际安装位置
python3 "$SKILL/scripts/ocr_case_pdfs.py" --check-tools
# 期望：ocrmypdf/tesseract/gs/qpdf 四项均有路径，无 MISSING（unpaper 可以 MISSING）
python3 "$SKILL/scripts/paddle_searchable_pdf.py" --check-tools
# 期望：python 指向 ~/.case-pdf-ocr/paddle/bin/python；paddleocr/pypdf/reportlab 等均有版本号；font 为 CaseOCR-CJK
```

两项自检都通过即安装完成。向用户报告结果，并告诉用户以后这样使用：

> 用 chinese-lawyer-case-ocr-skill 对 <案卷文件夹路径> 做 OCR。

## 环境变量（通常不需要）

- `CASE_OCR_PYTHON`：基础依赖 Python 解释器（默认自动探测 `~/.case-pdf-ocr/venv`）。
- `CASE_OCR_PADDLE_ROOT`：PaddleOCR 虚拟环境目录（默认自动探测 `~/.case-pdf-ocr/paddle`）。

## 故障排查

- 依赖细节、OCRmyPDF 参数、缓存与兜底策略：见 `chinese-lawyer-case-ocr-skill/references/install-and-fallbacks.md`。
- PaddleOCR 首次运行报模型/网络错误：说明模型尚未缓存，允许联网重试一次即可。
- 任何工具缺失时不要假装 OCR 成功——如实告知用户缺什么、装什么。

## 红线

未经用户明确授权，绝不把案卷 PDF 上传到任何云端 OCR 服务。全部处理必须在本机完成。
