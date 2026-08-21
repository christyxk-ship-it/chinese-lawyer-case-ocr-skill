# 中文律师案卷 OCR

在 Mac 本机把扫描 PDF 转成可搜索 PDF，同时生成逐页 Markdown 和一份质检报告。原件不改，案卷不上传。

## 特点

特别为中文诉讼律师、尤其是刑辩律师的需求设计。

- 为避免 AI 幻觉，不使用任何生成式视觉大模型；OCR 仍可能错字或漏字，法律要素必须人工复核。
- 先用 OCRmyPDF/Tesseract 批量打底，质检报告逐页标出低文本等疑难页；需要时再用评估脚本给出逐页建议，只对必要页面使用 PaddleOCR，不整卷重跑。

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
- 2026-08-21 Codex 完成 pypdf 安全补丁与完整 Paddle 回归；产物：`requirements-base.txt`、`requirements-paddle.txt`、`RELEASE_NOTES.md`。
- 2026-08-21 Claude 新增 OCR 产物回归测试，用固定样本拦截依赖升级导致的静默劣化；缺 OCR 工具时自动跳过。产物：`tests/test_ocr_regression.py`、`tests/fixtures/`。
- 2026-08-21 Claude 处理 Dependabot 升级：pypdfium2 5.13.0 经本机回归后合入；numpy 2.5.2 因与 paddlex 的 `numpy<2.4` 冲突而关闭，并在 `requirements-paddle.txt` 标注该上限。
