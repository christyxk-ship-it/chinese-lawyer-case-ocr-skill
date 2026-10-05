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
- 2026-08-21 Claude 首次月度上游巡查：待办 PR/Issue 均为空。经 PyPI 核实 paddleocr/paddlepaddle/pypdf/pypdfium2 均为最新版，无需改动。ocrmypdf/tesseract/ghostscript 不是 pip 包、仓库不锁版本，经 Homebrew 与 GitHub 安全公告核实：两条 Tesseract 漏洞（GHSA-7j76-5rq5-5jg8、GHSA-x3vq-7rr7-5x3h，均已在 5.5.3 修复）须靠伪造 `.traineddata` 模型文件触发，OCRmyPDF 一条（GHSA-jr24-5gpp-fwx7，已在 17.10.0 修复）只影响未使用的 `watcher.py` 热文件夹功能，均不影响本 skill 实际用法；Homebrew 当前稳定版已是修复版本，新装用户不受影响，故无仓库改动。扫过一轮新上游 OCR 项目，本月新增关注度集中在生成式视觉大模型（Surya、dots.ocr、PaddleOCR-VL 等），按本 skill 防幻觉原则一律排除；未发现符合"完全本地、非生成式、许可证允许商用"且优于现有方案的新项目。
- 2026-09-01 Claude 处理 Dependabot 四个升级：`pypdf` 6.16.2、`reportlab` 5.0.1、`numpy`（仅 base 路线）2.5.2，均在隔离环境装新版跑回归后合入；`codeql-action` 的 init 与 analyze 被拆成两个 PR，任一单独合并都会版本不一致致 CI 失败，改为一次提交同升到 4.37.9。同时给 Dependabot 加分组（每月每类只提一个 PR）、把 `numpy` 移出其管辖，并新增上限守卫测试，防止 paddlex 的 `numpy<2.4` 再被误升。产物：`requirements-base.txt`、`requirements-paddle.txt`、`.github/dependabot.yml`、`.github/workflows/codeql.yml`、`tests/test_cli.py`。
- 2026-09-07 Claude 月度上游巡查：待办 PR/Issue 均为空。经 PyPI 核实 paddlepaddle 3.3.1、paddleocr 3.7.0 均已是最新版；ocrmypdf/tesseract/ghostscript 不是 pip 包，经 Homebrew 核实分别为 17.11.0、5.5.3、10.07.1。另查到一条与本 skill 无关的误报——CVE-2026-26832 影响的是 npm 包 `node-tesseract-ocr`（Node.js 命令行包装器），不是本 skill 调用的 Tesseract 二进制本体，故不涉及。Ghostscript 的 CVE-2025-59798（栈缓冲区溢出）已在 10.05.2 修复，当前 Homebrew 稳定版远高于该版本，无需改动。扫过一轮新上游 OCR 项目：本月新增关注集中在生成式视觉大模型（Baidu Unlimited-OCR、DeepSeek-OCR 2、dots.mocr、GLM-OCR 等），按本 skill 防幻觉原则一律排除；未发现符合"完全本地、非生成式、许可证允许商用"且优于现有 PaddleOCR/Tesseract 组合的新项目。

- 2026-09-08 Codex 按潜川授权，将本机五处 OCR Skill 部署统一为 GitHub main c3158e9 对应的完整 Skill 包，四运行时目录软链、WorkBuddy 同哈希副本；现有两条 OCR 运行路线工具自检通过，未推送仓库。验收记录留存本机。
- 2026-09-22 Claude 修复 iCloud「桌面与文稿」同步文件夹里 OCR 成果在访达中看不见：处理中临时文件名原以「.」开头，处理稍久就会被系统标为隐藏，改名为正式成果后仍隐藏；现改为以原文件名开头，本机新旧版对照实测确认。旧版成果看不见时，恢复办法见说明文件「失败处理」一节。产物：`chinese-lawyer-case-ocr-skill/scripts/`、`chinese-lawyer-case-ocr-skill/references/install-and-fallbacks.md`。
- 2026-09-22 Claude 更正 2026-09-08 Codex 那条：删去其中本机绝对路径，改为「验收记录留存本机」，结论未动；另打开 GitHub 仓库「合并后自动删除分支」设置，合并完的临时分支不再堆积。产物：`README.md`。
- 2026-10-03 Claude 云端月度上游巡查：待办 Issue 为空，Dependabot 有两个待处理 PR（pypdf 6.16.2→6.19.0、GitHub Actions 两项更新），由维护者按惯例经回归后处理。经 PyPI 两个独立端点（JSON 接口与包索引页）核实：ocrmypdf 17.13.0、paddleocr 3.7.0、paddlepaddle 3.3.1、pypdf 6.19.0、pypdfium2 5.13.0；paddleocr、paddlepaddle、pypdfium2 与仓库锁定版本一致，PyPI 对 pypdf 未登记安全公告。云端未能核实：Homebrew（ocrmypdf/tesseract/ghostscript 当前版本）、GitHub 安全公告与各项目发布页、上游新 OCR 项目扫描（网络被拦或超出本次访问范围），不凭记忆补数字，请维护者在本机补查。除上述待补查项外，无值得行动的发现。
