#!/usr/bin/env bash
# 中文律师案卷 OCR 技能包 一键安装（macOS）
# 等价于 INSTALL.md 的自动化版本；出错即停，报错信息如实显示。
set -euo pipefail

say() { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31m错误: %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(uname -s)" = "Darwin" ] || die "本脚本仅支持 macOS"
command -v brew >/dev/null 2>&1 || die "未安装 Homebrew，请先安装：https://brew.sh 或改用 INSTALL.md 由 AI 助手安装"

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_SRC="$REPO_DIR/chinese-lawyer-case-ocr-skill"
[ -d "$SKILL_SRC" ] || die "找不到 skill 目录：$SKILL_SRC"

say "1/5 安装命令行工具（ocrmypdf / qpdf / ghostscript / tesseract）"
brew install ocrmypdf qpdf ghostscript tesseract tesseract-lang
tesseract --list-langs | grep -q chi_sim || die "tesseract 缺少中文包 chi_sim"

say "2/5 创建基础 Python 环境（~/.case-pdf-ocr/venv）"
python3 -m venv "$HOME/.case-pdf-ocr/venv"
"$HOME/.case-pdf-ocr/venv/bin/pip" install --quiet --upgrade pip
"$HOME/.case-pdf-ocr/venv/bin/pip" install --quiet numpy pypdf pypdfium2 pillow reportlab

say "3/5 创建 PaddleOCR 环境（~/.case-pdf-ocr/paddle，约 1–2 GB，请耐心等待）"
python3 -m venv "$HOME/.case-pdf-ocr/paddle"
"$HOME/.case-pdf-ocr/paddle/bin/pip" install --quiet --upgrade pip
"$HOME/.case-pdf-ocr/paddle/bin/pip" install --quiet paddlepaddle paddleocr numpy pypdf pypdfium2 pillow reportlab safetensors

say "4/5 安装 skill 到 AI 助手技能目录"
INSTALLED=""
for base in "$HOME/.workbuddy/skills" "$HOME/.codex/skills" "$HOME/.claude/skills"; do
  parent="$(dirname "$base")"
  if [ -d "$parent" ]; then
    mkdir -p "$base"
    rm -rf "$base/chinese-lawyer-case-ocr-skill"
    cp -R "$SKILL_SRC" "$base/chinese-lawyer-case-ocr-skill"
    echo "已安装到 $base/chinese-lawyer-case-ocr-skill"
    INSTALLED="$base/chinese-lawyer-case-ocr-skill"
  fi
done
[ -n "$INSTALLED" ] || die "未找到 WorkBuddy/Codex/Claude 的配置目录，请手动复制 skill 目录（见 INSTALL.md 第 4 步）"

say "5/5 自检"
python3 "$INSTALLED/scripts/ocr_case_pdfs.py" --check-tools

say "安装完成。使用方式：对你的 AI 助手说——用 chinese-lawyer-case-ocr-skill 对 <案卷文件夹路径> 做 OCR。"
