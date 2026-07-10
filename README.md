# 中文律师案卷 OCR 技能包

把扫描件、图片型的中文法律案卷 PDF，在**你自己的电脑上**转成**可搜索、可复制文字**的 PDF，并附带一份同名 Markdown 文本副本和逐页质检报告。

给你的 AI 助手（WorkBuddy、Codex、Claude Code 等）装上这个技能包，之后只要说一句"帮我 OCR 这个案卷文件夹"，剩下的它自己完成。

## 为什么律师需要它

- **保密：全程本地处理，绝不上传**：案卷不出电脑，没有云端 OCR 的保密风险。
- **人机共读：交付的是可检索 PDF和MD文件**，可检索PDF：满足律师阅卷习惯，轻松批注、摘要；同时MD文件给Agent阅读，辅助生成办案文件。
- **自带质检闭环**：逐页文字量清单、结构检查、双提取器验收、失败清单——哪页识别不好，报告会告诉你，不必逐页肉眼排查。
- **省算力的分流设计**：先逐页评估，普通页用快速引擎批量跑，疑难页（表格、横页、低质量扫描）才动用高精度引擎。

## 系统要求

- macOS（Apple 芯片或 Intel 均可）
- 一个能执行本地命令的 AI 助手：WorkBuddy / Codex / Claude Code 任选
- 首次安装需联网（下载 OCR 引擎和模型，之后完全离线可用）

## 安装（一步，不需要懂技术）

1. 把下载链接发给你的Agent（Codex，Claude，workbuddy），告诉它：安装本Skill并适配。即可。下载链接：https://github.com/christyxk-ship-it/chinese-lawyer-case-ocr-skill

（AI 助手看这里：请克隆或下载本仓库，阅读 `INSTALL.md` 并严格按步骤安装、自检，完成后向用户报告结果。）

## 怎么用

打开案卷 PDF 所在文件夹，对你的 AI 说：

> 用 chinese-lawyer-case-ocr-skill 对 <案卷文件夹路径> 做 OCR。

完成后得到：

```text
案卷文件夹/
├── OCR成果/
│   ├── 某某卷宗_OCR.pdf   ← 可搜索 PDF（唯一最终交付件）
│   └── 某某卷宗_OCR.md    ← 逐页文本副本（全文检索、引用摘录用）
└── OCR过程文件/
    ├── 报告/               ← 评估、清单、质检报告、日志
    ├── 底稿/               ← 方向/水印修正的无文字层底稿
    ├── 转写/               ← 高精度引擎的逐页转写与坐标
    └── 缓存/               ← 仅全局缓存不可用时使用
```

## 常见问题

- **文件会被上传吗？** 不会。OCR 引擎（OCRmyPDF/Tesseract、PaddleOCR）全部跑在本机，"未经授权不上传案卷"是本技能包写死的红线。
- **首次运行为什么要联网？** 只为下载一次 OCR 模型（保存在本机全局缓存），之后离线可用。
- **识别不准的页怎么办？** 看 `OCR过程文件/报告/OCR质量检查.md`，低文本页会被列出来供人工核对；手写和印章内容建议始终以原图为准。

## 目录结构

```text
chinese-lawyer-case-ocr-skill/   ← skill 本体（SKILL.md + 脚本 + 参考文档）
INSTALL.md                       ← 给 AI 助手看的安装说明
install.sh                       ← 一键安装脚本（可选）
tools/                           ← 维护者工具
```

## 维护同步（仓库维护者用）

本机源 skill 位于 `~/.codex/skills/case-pdf-ocr`，公开仓库使用机器名 `chinese-lawyer-case-ocr-skill`，不要整目录直接覆盖，用同步脚本：

```bash
python3 tools/sync_from_local_skill.py            # 同步并校验
python3 tools/sync_from_local_skill.py --commit --push
```

## 许可

MIT License，详见 `LICENSE`。欢迎复制链接转发给需要的同行，我会继续维护和迭代。
