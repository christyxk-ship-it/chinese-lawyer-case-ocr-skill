# 中文律师案卷 OCR

在 Mac 本机把扫描 PDF 转成可搜索 PDF，同时生成逐页 Markdown 和一份质检报告。原件不改，案卷不上传。

## 特点

- OCRmyPDF/Tesseract 批量处理，疑难页可选 PaddleOCR。
- 不使用生成式视觉模型；OCR 仍可能错字或漏字，法律要素必须人工复核。
- 案卷目录只保留一个 `OCR成果/`，不生成过程文件夹。
- 安装时明确选择宿主，已有 Skill 先备份，失败自动恢复。

## 系统

- macOS、Python 3.12 或 3.13、Homebrew。
- Apple 芯片支持完整路线。
- Intel Mac 支持 OCRmyPDF 基础路线；PaddlePaddle 当前已停止官方 x86_64 支持。
- 首次安装依赖及首次使用 PaddleOCR 下载模型时需要联网；模型就绪后可离线处理。

## 安装

把下面这句话交给能执行本地命令的 Codex、WorkBuddy 或 Claude Code：

> 下载 https://github.com/christyxk-ship-it/chinese-lawyer-case-ocr-skill ，阅读 INSTALL.md，并只安装到你自己的宿主目录，完成两项自检后报告结果。

安装器示例：

```bash
./install.sh --target codex
```

可选目标：`codex`、`workbuddy`、`claude`；需要多个宿主时重复写 `--target`。

## 使用

对 Agent 说：

> 用 chinese-lawyer-case-ocr-skill 处理这个案卷文件夹。

得到：

```text
案卷文件夹/
└── OCR成果/
    ├── 某卷_OCR.pdf
    ├── 某卷_OCR.md
    └── OCR质检报告.md
```

命令退出码非零、报告存在失败项或要害页文字异常时，不得认定完成。

## 维护

仓库中的 `chinese-lawyer-case-ocr-skill/` 是事实源：

```bash
python3 tools/sync_from_local_skill.py
```

从另一份独立副本回灌时才使用 `--source`；提交和推送仍须显式加 `--commit --push`。

MIT License。

## 进展日志

- 2026-08-21 Codex 修复维护脚本的同源风险并发布 `3fed354`。
- 2026-08-21 Codex 完成 v0.4.0 安全与简洁化改造并通过本地回归；产物：`chinese-lawyer-case-ocr-skill/`、`install.sh`、`tests/`。
