#!/usr/bin/env bash
set -euo pipefail

say() { printf '\n==> %s\n' "$*"; }
die() { printf '\n错误：%s\n' "$*" >&2; exit 1; }

usage() {
  cat <<'EOF'
用法：./install.sh --target codex|workbuddy|claude [--target ...]

必须明确选择安装宿主；已有同名 Skill 会先备份，不会直接删除。
EOF
}

targets=()
while [ "$#" -gt 0 ]; do
  case "$1" in
    --target)
      [ "$#" -ge 2 ] || die "--target 后缺少宿主名"
      targets+=("$2")
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "未知参数：$1"
      ;;
  esac
done

[ "${#targets[@]}" -gt 0 ] || die "请用 --target 明确选择宿主"
[ "$(uname -s)" = "Darwin" ] || die "本脚本仅支持 macOS"

repo_dir="$(cd "$(dirname "$0")" && pwd)"
skill_source="$repo_dir/chinese-lawyer-case-ocr-skill"
base_requirements="$repo_dir/requirements-base.txt"
paddle_requirements="$repo_dir/requirements-paddle.txt"
[ -f "$skill_source/SKILL.md" ] || die "找不到 Skill：$skill_source"
[ -f "$base_requirements" ] || die "找不到依赖锁文件：$base_requirements"

for target in "${targets[@]}"; do
  case "$target" in
    codex|workbuddy|claude) ;;
    *) die "不支持的宿主：$target" ;;
  esac
done

if ! command -v brew >/dev/null 2>&1; then
  die "未找到 Homebrew。请让 AI 助手按 INSTALL.md 引导安装后重试。"
fi

missing_tools=0
for tool in ocrmypdf qpdf gs tesseract; do
  command -v "$tool" >/dev/null 2>&1 || missing_tools=1
done
if command -v tesseract >/dev/null 2>&1 && ! tesseract --list-langs 2>/dev/null | grep -qx chi_sim; then
  missing_tools=1
fi
if [ "$missing_tools" -eq 1 ]; then
  say "安装缺失的本地 OCR 工具"
  brew install ocrmypdf qpdf ghostscript tesseract tesseract-lang
else
  say "本地 OCR 工具已齐全，跳过 Homebrew 安装"
fi

python_bin="$(command -v python3 || true)"
if [ -z "$python_bin" ] || ! "$python_bin" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] in {(3, 12), (3, 13)} else 1)'; then
  say "安装 Python 3.12"
  brew install python@3.12
  python_bin="$(brew --prefix)/opt/python@3.12/bin/python3.12"
fi

runtime_root="$HOME/.case-pdf-ocr"
backup_stamp="$(date +%Y%m%d-%H%M%S)-$$"
backup_root="$runtime_root/backups/$backup_stamp"
mkdir -p "$runtime_root" "$backup_root"

changed_destinations=()
changed_backups=()
staged_paths=()
install_ok=0

rollback_on_exit() {
  local status=$?
  trap - EXIT
  set +e
  if [ "$install_ok" -eq 0 ] && [ "${#changed_destinations[@]}" -gt 0 ]; then
    printf '\n安装未完成，开始恢复原状态。\n' >&2
    local index destination backup failed
    for ((index=${#changed_destinations[@]}-1; index>=0; index--)); do
      destination="${changed_destinations[$index]}"
      backup="${changed_backups[$index]}"
      failed="$backup_root/failed-new-$index"
      [ ! -e "$destination" ] || mv "$destination" "$failed"
      [ ! -e "$backup" ] || mv "$backup" "$destination"
    done
  fi
  if [ "$install_ok" -eq 0 ] && [ "${#staged_paths[@]}" -gt 0 ]; then
    local staged_index staged_path
    for ((staged_index=0; staged_index<${#staged_paths[@]}; staged_index++)); do
      staged_path="${staged_paths[$staged_index]}"
      [ ! -e "$staged_path" ] || mv "$staged_path" "$backup_root/failed-stage-$staged_index"
    done
  fi
  exit "$status"
}
trap rollback_on_exit EXIT

install_environment() {
  local name="$1"
  local requirements="$2"
  local destination="$runtime_root/$name"
  local staged="$runtime_root/.${name}.stage.$$.${RANDOM}"
  local backup="$backup_root/environment-$name"
  staged_paths+=("$staged")

  if [ -x "$destination/bin/python" ] \
    && [ -f "$destination/.case-ocr-requirements.txt" ] \
    && cmp -s "$requirements" "$destination/.case-ocr-requirements.txt" \
    && "$destination/bin/pip" check >/dev/null 2>&1; then
    say "锁定依赖环境未变化，沿用：$name"
    return
  fi

  say "构建锁定依赖环境：$name"
  "$python_bin" -m venv "$staged"
  "$staged/bin/pip" install --quiet "pip==26.1.2"
  "$staged/bin/pip" install --quiet --requirement "$requirements"
  "$staged/bin/pip" check
  cp "$requirements" "$staged/.case-ocr-requirements.txt"

  if [ -e "$destination" ]; then
    [ ! -L "$destination" ] || die "拒绝替换符号链接：$destination"
    mv "$destination" "$backup"
  fi
  if ! mv "$staged" "$destination"; then
    [ ! -e "$backup" ] || mv "$backup" "$destination"
    die "环境安装失败，已恢复原环境：$name"
  fi
  changed_destinations+=("$destination")
  changed_backups+=("$backup")
}

install_environment "venv" "$base_requirements"

machine="$(uname -m)"
paddle_enabled=0
if [ "$machine" = "arm64" ]; then
  install_environment "paddle" "$paddle_requirements"
  paddle_enabled=1
else
  say "Intel Mac 仅启用 OCRmyPDF 基础路线；当前 PaddlePaddle 已停止官方 x86_64 支持"
fi

target_path() {
  case "$1" in
    codex) printf '%s\n' "$HOME/.codex/skills/chinese-lawyer-case-ocr-skill" ;;
    workbuddy) printf '%s\n' "$HOME/.workbuddy/skills/chinese-lawyer-case-ocr-skill" ;;
    claude) printf '%s\n' "$HOME/.claude/skills/chinese-lawyer-case-ocr-skill" ;;
  esac
}

install_skill() {
  local host="$1"
  local destination
  destination="$(target_path "$host")"
  local parent
  parent="$(dirname "$destination")"
  local staged="$parent/.chinese-lawyer-case-ocr-skill.stage.$$.${RANDOM}"
  local backup="$backup_root/${host}-skill"
  staged_paths+=("$staged")

  if [ -d "$destination" ] && [ ! -L "$destination" ] && diff -qr "$skill_source" "$destination" >/dev/null 2>&1; then
    printf '已是相同版本：%s\n' "$destination"
    return
  fi
  mkdir -p "$parent" "$staged"
  cp -R "$skill_source"/. "$staged"/
  "$runtime_root/venv/bin/python" -c 'import ast,pathlib,sys; [ast.parse(p.read_text(encoding="utf-8"), filename=str(p)) for p in pathlib.Path(sys.argv[1]).glob("scripts/*.py")]' "$staged"

  if [ -e "$destination" ]; then
    [ ! -L "$destination" ] || die "拒绝替换符号链接：$destination"
    mv "$destination" "$backup"
  fi
  if ! mv "$staged" "$destination"; then
    [ ! -e "$backup" ] || mv "$backup" "$destination"
    die "Skill 安装失败，已恢复原版本：$host"
  fi
  changed_destinations+=("$destination")
  changed_backups+=("$backup")
  printf '已安装：%s\n' "$destination"
}

for target in "${targets[@]}"; do
  install_skill "$target"
done

say "自检"
first_skill="$(target_path "${targets[0]}")"
"$runtime_root/venv/bin/python" "$first_skill/scripts/ocr_case_pdfs.py" --check-tools
if [ "$paddle_enabled" -eq 1 ]; then
  "$runtime_root/paddle/bin/python" "$first_skill/scripts/paddle_searchable_pdf.py" --check-tools
fi

say "安装完成"
printf '备份：%s\n' "$backup_root"
printf '使用：让 AI 助手用 chinese-lawyer-case-ocr-skill 处理案卷文件夹。\n'
install_ok=1
