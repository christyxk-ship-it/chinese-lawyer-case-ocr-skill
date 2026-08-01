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

主路线 OCRmyPDF 跑完后，对疑难材料使用 PaddleOCR，尤其是截图、复杂表格、印章、低质量扫描件，以及 Tesseract 提取文字异常偏少的文件。PaddleOCR 有两条路线，作用不同：`paddleocr_extract.py` 只生成文本和 JSON/坐标副本，供审阅比对，不是最终交付件；`paddle_searchable_pdf.py` 生成可搜索 PDF，验收通过后可以作为最终件替换基础 OCR 版本。

如果目标是更干净的可搜索 PDF，而不是只要文本/坐标，使用 `scripts/paddle_searchable_pdf.py`。该路线借鉴了逐行 bbox 叠加隐形文字层的做法，识别更干净，但速度慢、耗算力更高，只用于核心文件、疑难页或低质量输出的二次增强：

```bash
python3 scripts/paddle_searchable_pdf.py "input.pdf" "output_可搜索.pdf" --profile balanced --dump-text "output_转写.txt"
python3 scripts/paddle_searchable_pdf.py "input.pdf" "output_可搜索.pdf" --profile fast --pages 1-3,8
python3 scripts/paddle_searchable_pdf.py "input.pdf" "output_可搜索.pdf" --profile careful --lang chinese_cht
```

PaddleOCR 可搜索 PDF 档位：

- `--profile fast`：渲染倍率 1.8，适合抽样页、质量复核和大文件局部增强。
- `--profile balanced`：渲染倍率 2.2，默认建议档，适合重要 PDF 的完整增强。
- `--profile careful`：渲染倍率 2.6，小字、表格密集或扫描质量差时使用；更慢。

**倍率与底稿分辨率的落差（实测教训）**：三个档位的渲染倍率都低于 `gs -r300` 底稿的原生倍率（约 4.2），即便 `careful` 也是在降采样。密排正文页不受影响，但**宽字距的落款/签章页会整列漏字**——竖排"审判长／审判员"职务栏读得出来，右侧姓名列却整体丢失。实测把 `--scale` 提到 4.2 也只捞回部分字。此时：

- 该类页改用 Tesseract `--psm 6`（稀疏宽字距版式上明显更稳），但它同样会认错字，须逐字对照原图。
- 两条路线都不完整时，**在质检报告里以"人工核对结果"单列，并注明该内容不在 PDF 文字层内、检索不到**。不要手工往文字层里补字：那是转写，不是识别，会让成果的可信边界变得不可分辨。
- 落款页文字量天然就少，`page_text_manifest.csv` 报低文本属正常，但必须逐页看图确认是"页面内容本身少"，而不是漏识别。

**成果体积膨胀**：`paddle_searchable_pdf.py` 的输入是 `-sDEVICE=pdfimage24` 无压缩位图底稿，成果通常比原件涨 3–4 倍（实测 68 页案卷 28MB → 123MB）。收尾用 pdfwrite 重编码到 200dpi/DCTEncode/q88 可压回 40MB 上下，文字层与页数无损，与 300dpi 肉眼无差，命令见 SKILL.md 第 4 步。案卷要寄检察院、上传或邮件外发时不要省这步。

节省算力原则：能只跑低文本页、表格页、核心证据页，就不要全文件跑；能用 `--profile fast` 判断质量，就不要直接上 `careful`；能用 OCRmyPDF 达标，就不要重复跑 PaddleOCR。

方向、水印或旧文字层处理原则：PaddleOCR 生成可搜索 PDF 时，选中页应来自视觉方向正确、无旧文字层的图片底稿。修复已有 OCR 成品时，先把需要重做的页输出到 `OCR过程文件/底稿/`（qpdf 修方向 + gs 栅格化，见 SKILL.md 第 3 步），再用 `--fail-if-selected-has-text` 防止把新文字层叠到旧文字层上。

方向陷阱（实测教训）：很多证件/扫描 PDF 是"横向存储 + /Rotate 标记正立显示"。gs 栅格化按显示方向渲染、自动消化 /Rotate，所以显示正立的页**直接 gs 即可**；若误加 `qpdf --rotate`，旋转标记归零后内容就以横向裸奔，成果整体转倒。`--rotate` 只用于阅读器里显示方向本身不正的页。

PaddleOCR 环境位置（脚本按此顺序自动探测）：

1. 环境变量 `CASE_OCR_PADDLE_ROOT` 指定的目录
2. `~/.case-pdf-ocr/paddle`（标准安装位置，INSTALL.md 创建）
3. `~/Codex/tools/paddleocr`（本机统一工具位置）

基础依赖解释器同理：`CASE_OCR_PYTHON` > `~/.case-pdf-ocr/venv` > Codex 捆绑运行时 > 当前解释器。

已验证版本：`paddleocr==3.7.0`、`paddlepaddle==3.3.1`（Apple 芯片）。

Intel Mac 说明：paddlepaddle 3.1+ 只提供 Apple 芯片轮子，Intel 机只能装 3.0.0，其静态推理引擎与 PP-OCRv6 模型不兼容（strides 报错）。`paddle_searchable_pdf.py` 检测到该错误会自动切换动态引擎重试（依赖 safetensors 包，INSTALL.md 已包含）。Python 3.9 实测可跑通整个 Paddle 栈。

常用检查：

```bash
python3 scripts/paddleocr_extract.py --check-tools
python3 scripts/paddleocr_extract.py "/path/to/case-folder" --max-files 1
```

PaddleOCR 脚本探测到上述任一环境的 `bin/python` 时，会自动用该 Python 重新执行自己。缓存默认逻辑：优先使用 PaddleOCR 环境目录下的全局 `cache/`（模型只下载/保存一份，不逐案卷复制）；该位置不可写时才退回案卷根目录下的 `OCR过程文件/缓存/`；也可用 `--cache-dir` 显式指定。首次运行需联网下载一次 OCR 模型，之后完全离线。

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
ocrmypdf -l chi_sim+eng --skip-text --output-type pdf --jobs 4 --optimize 0 --tesseract-timeout 30 --tesseract-non-ocr-timeout 5 input.pdf output.pdf
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
- `--profile troubleshoot`：顽固 PDF，先清理输入，单线程跑，单文件上限 600 秒。

超时策略：`fast`/`balanced`/`careful` 均不设文件级超时（大文件跑几十分钟属正常），防卡死靠单页上限——`fast` 30 秒、`troubleshoot` 30 秒、`balanced`/`careful` 不限。仅 `troubleshoot` 保留 600 秒文件上限。注意文件级超时一旦触发即全损：脚本会杀掉进程并删除半成品，重跑从第一页开始。

`careful` 档位只有在本机存在 `unpaper` 时才自动启用 `--clean-final`。如果缺少 `unpaper`，不要让 OCR 因清理步骤失败而中断；首要目标仍然是生成可检索 PDF。只有用户明确要求更强清理效果时，才考虑安装 `unpaper` 后重跑。

脚本每处理一个文件就写入 `ocr_manifest.csv`（与既有记录合并，分批运行不丢历史行）；默认跳过既有 `ok`/`exists` 记录；除非传入 `--no-sidecar-text`，否则在 `OCR成果/` 生成 `<原名>_OCR.md` 文本副本；除非传入 `--no-pdf-check`，否则对 OCR 输出运行 `qpdf --check`；每次都会写入 `page_text_manifest.csv` 逐页文字量清单；最后写入 `OCR质量检查.md`。

完成判断以 `OCR成果/` 中的可搜索 PDF 为准：文件必须存在、可打开、可检索，通过结构检查，并通过逐页文字层检查。PaddleOCR 转写、JSON 结构和各类报告只用于质检、检索辅助和疑难材料增强，统一归入 `OCR过程文件/`。

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
- **文字层码位异常**：汉字落在康熙部首区或 CJK 兼容区（`⼈` `⺠` `⻄` `⽂` `⽉`），或数字被逐字符拆开（`2 0 2 1年1⽉4 ⽇`）。这类成果人眼看着完全正常，检索却整片失效——实测一份判决书 7.9% 的字符是康熙部首，搜"人民法院""人民检察院""非法获取国家秘密"命中全为 0。接手他人或旧流程产出的"可搜索 PDF"时，这是第一顺位的复核项，也是判断要不要推倒重做的依据。检查脚本见 SKILL.md 第 5 步；**必须按 `ord()` 判四段码位（U+2E80–2EFF、U+2F00–2FDF、U+F900–FAFF、U+FE30–FE4F），不要写字面量区间正则**——把兼容表意文字区写成 `豈-﫿` 会把 `银` `鉴` `部` 这类正常汉字一并吞掉，导致大规模误报。
- 表格、手写内容、印章、身份证件或照片是重要证据。
- 印章覆盖处的文字（合议庭姓名、裁判日期）识别不出属常态，须标"待核验"并提示查纸质原件，不得依上下文推断补全。
- 文件加密、损坏或页面尺寸异常。
- OCRmyPDF 日志出现元数据 `UnicodeDecodeError`；用 `--sanitize-input always` 或 `--profile troubleshoot` 重跑。

对大型案件材料，先报告确切读取缺口，再用关键词、日期、人名、案号、金额和证据编号做定向提取。

## 速度、准确率与 token 策略

- 批量默认：OCRmyPDF/Tesseract。它最快、最省算力，适合先把整批案卷变成可检索 PDF。
- 质量增强：PaddleOCR 可搜索 PDF。只对核心证据、疑难页、Tesseract 低文本/乱码文件使用。
- 抽样优先：先用 `scan-only`、清单、关键词和少量页测试判断质量，再决定是否全文件增强。
- 少读文本：不要把 OCR 全文塞进对话。产出文本副本后，用 `rg`、页码、关键词、金额、人名、案号做定向检索。
- 少重跑：尊重 manifest 和已存在输出；除非参数或质量目标改变，不要 `--overwrite`。
