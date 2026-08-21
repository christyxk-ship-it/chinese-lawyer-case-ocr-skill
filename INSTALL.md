# 安装说明（给执行安装的 Agent）

目标平台是 macOS。安装会写入 `~/.case-pdf-ocr/` 和用户明确选择的一个或多个宿主目录；执行前说明这些变更并取得用户同意。

## 1. 前提

先检查：

```bash
uname -s
brew --version
```

必须是 macOS，并已安装 Homebrew。没有 Homebrew 时停止，向用户说明需要其本人完成官方安装，不索要或代输系统密码。

## 2. 安装

必须显式选择宿主：

```bash
./install.sh --target codex
./install.sh --target workbuddy
./install.sh --target claude
```

多个宿主可写在同一条命令中，例如 `--target codex --target claude`。不得自行扩大目标。

安装器会：

- 只补装缺失的本地 OCR 工具；
- 使用固定核心依赖版本建立 Python 3.12/3.13 环境；
- 比较 Skill，已有版本先备份到 `~/.case-pdf-ocr/backups/<时间>/`；
- 任一步失败时恢复本轮已替换的环境和 Skill；
- 运行 OCRmyPDF 与 PaddleOCR 自检。

Intel Mac 只安装 OCRmyPDF 基础路线，不安装当前官方已停止支持的 PaddlePaddle x86_64 版本。

## 3. 验收

安装命令必须以退出码 0 结束。也可再次运行：

```bash
python3 <Skill目录>/scripts/ocr_case_pdfs.py --check-tools
python3 <Skill目录>/scripts/paddle_searchable_pdf.py --check-tools
```

任一命令非零即未完成；不得只看到部分版本号就报告成功。Intel Mac 不要求第二项。

## 4. 数据边界

依赖和 Paddle 模型会联网下载，但 OCR 输入不会上传。未经用户针对具体文件明确授权，不得改用任何云端 OCR 服务。
