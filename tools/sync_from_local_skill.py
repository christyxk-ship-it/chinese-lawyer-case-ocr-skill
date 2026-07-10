#!/usr/bin/env python3
"""Sync the local case-pdf-ocr skill into this public GitHub package.

The local source skill uses the private Codex name `case-pdf-ocr`. The public
package must keep the machine name `chinese-lawyer-case-ocr-skill`, so this
script copies resources but rewrites the SKILL.md frontmatter.
"""

from __future__ import annotations

import argparse
import ast
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


RELEASE_SKILL_NAME = "chinese-lawyer-case-ocr-skill"
RELEASE_DESCRIPTION = (
    "在本地把扫描件/图片型中文法律案卷 PDF 转成可检索 PDF 并质检。当用户要求 OCR 案卷、"
    "让判决书等扫描 PDF 可搜索/可复制文字、给 PDF 加文字层，或提供的 PDF 无法选中文字时使用。"
)
AGENT_OPENAI_YAML = """interface:
  display_name: "中文执业律师案卷OCR-SKILL"
  short_description: "中文法律案卷 OCR，生成可检索 PDF，并逐页质检文字层"
  default_prompt: "使用 $chinese-lawyer-case-ocr-skill 对中文法律案卷 PDF 做 OCR：先评估分流，再用 OCRmyPDF/Tesseract 批量生成可检索 PDF；对核心、横向、低文本或疑难页面用 PaddleOCR 增强；最终只保留一份可搜索 PDF，并输出逐页文字层质检报告。"
"""

DEFAULT_SOURCE = Path.home() / ".codex" / "skills" / "case-pdf-ocr"
DEFAULT_REPO = Path(__file__).resolve().parents[1]
PUBLISHED_SKILL_DIR = "chinese-lawyer-case-ocr-skill"
SYNC_PATHS = [
    Path(PUBLISHED_SKILL_DIR) / "SKILL.md",
    Path(PUBLISHED_SKILL_DIR) / "agents" / "openai.yaml",
    Path(PUBLISHED_SKILL_DIR) / "references",
    Path(PUBLISHED_SKILL_DIR) / "scripts",
]
IGNORE_NAMES = {"__pycache__", ".DS_Store"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync local case-pdf-ocr skill into the public package.")
    parser.add_argument("--source", default=str(DEFAULT_SOURCE), help="local source skill directory")
    parser.add_argument("--repo", default=str(DEFAULT_REPO), help="public release repository root")
    parser.add_argument("--commit", action="store_true", help="commit synced changes")
    parser.add_argument("--push", action="store_true", help="push committed changes to origin")
    parser.add_argument("--allow-dirty", action="store_true", help="allow pre-existing release repo changes")
    parser.add_argument("--no-validate", action="store_true", help="skip validation")
    return parser.parse_args()


def run(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, cwd=str(cwd), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and proc.returncode != 0:
        details = (proc.stdout + "\n" + proc.stderr).strip()
        raise SystemExit(f"command failed: {' '.join(cmd)}\n{details}")
    return proc


def git_lines(repo: Path, *args: str, check: bool = True) -> list[str]:
    proc = run(["git", *args], repo, check=check)
    return [line for line in proc.stdout.splitlines() if line.strip()]


def require_clean_repo(repo: Path, allow_dirty: bool) -> None:
    if allow_dirty:
        return
    dirty = git_lines(repo, "status", "--porcelain")
    if dirty:
        raise SystemExit("release repo has existing changes; commit/stash them or rerun with --allow-dirty")


def fast_forward_remote(repo: Path) -> None:
    run(["git", "fetch", "--prune", "origin"], repo)
    upstream = run(["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], repo, check=False)
    if upstream.returncode != 0:
        return
    counts = git_lines(repo, "rev-list", "--left-right", "--count", f"HEAD...{upstream.stdout.strip()}")[0]
    ahead, behind = (int(part) for part in counts.split())
    if ahead and behind:
        raise SystemExit("local and remote branches diverged; resolve manually before automated sync")
    if behind:
        run(["git", "pull", "--ff-only"], repo)


def ignore(src: str, names: list[str]) -> set[str]:
    return {name for name in names if name in IGNORE_NAMES or name.endswith(".pyc")}


def split_skill_body(text: str) -> str:
    if not text.startswith("---\n"):
        raise SystemExit("source SKILL.md must start with YAML frontmatter")
    parts = text.split("---", 2)
    if len(parts) != 3:
        raise SystemExit("source SKILL.md has invalid frontmatter")
    return parts[2]


def write_public_skill(source: Path, target: Path) -> None:
    target.write_text(expected_public_skill_text(source), encoding="utf-8")


def expected_public_skill_text(source: Path) -> str:
    body = split_skill_body((source / "SKILL.md").read_text(encoding="utf-8"))
    frontmatter = (
        "---\n"
        f"name: {RELEASE_SKILL_NAME}\n"
        f'description: "{RELEASE_DESCRIPTION}"\n'
        "---"
    )
    return frontmatter + body


def mirror_dir(source: Path, target: Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target, ignore=ignore)


def sync_files(source: Path, repo: Path) -> Path:
    public_skill = repo / PUBLISHED_SKILL_DIR
    if not source.exists():
        raise SystemExit(f"source skill not found: {source}")
    public_skill.mkdir(parents=True, exist_ok=True)
    write_public_skill(source, public_skill / "SKILL.md")
    mirror_dir(source / "scripts", public_skill / "scripts")
    mirror_dir(source / "references", public_skill / "references")
    (public_skill / "agents").mkdir(parents=True, exist_ok=True)
    (public_skill / "agents" / "openai.yaml").write_text(AGENT_OPENAI_YAML, encoding="utf-8")
    return public_skill


def relevant_files(base: Path) -> dict[Path, Path]:
    files: dict[Path, Path] = {}
    if not base.exists():
        return files
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        if any(part in IGNORE_NAMES for part in path.parts):
            continue
        if path.name.endswith(".pyc"):
            continue
        files[path.relative_to(base)] = path
    return files


def dirs_match(source: Path, target: Path) -> bool:
    source_files = relevant_files(source)
    target_files = relevant_files(target)
    if set(source_files) != set(target_files):
        return False
    return all(source_files[rel].read_bytes() == target_files[rel].read_bytes() for rel in source_files)


def public_package_matches(source: Path, repo: Path) -> bool:
    public_skill = repo / PUBLISHED_SKILL_DIR
    skill_path = public_skill / "SKILL.md"
    agent_path = public_skill / "agents" / "openai.yaml"
    if not skill_path.exists() or skill_path.read_text(encoding="utf-8") != expected_public_skill_text(source):
        return False
    if not agent_path.exists() or agent_path.read_text(encoding="utf-8") != AGENT_OPENAI_YAML:
        return False
    return dirs_match(source / "scripts", public_skill / "scripts") and dirs_match(
        source / "references", public_skill / "references"
    )


def validate(public_skill: Path, repo: Path) -> None:
    for py_file in sorted((public_skill / "scripts").glob("*.py")):
        ast.parse(py_file.read_text(encoding="utf-8"))
    validator = Path.home() / ".codex" / "skills" / ".system" / "skill-creator" / "scripts" / "quick_validate.py"
    if validator.exists():
        run([sys.executable, str(validator), str(public_skill)], repo)
    first_lines = (public_skill / "SKILL.md").read_text(encoding="utf-8").splitlines()[:3]
    if f"name: {RELEASE_SKILL_NAME}" not in first_lines:
        raise SystemExit("public SKILL.md name was not preserved")


def changed(repo: Path) -> bool:
    tracked = [str(path) for path in SYNC_PATHS]
    proc = run(["git", "status", "--porcelain", "--", *tracked], repo)
    return bool(proc.stdout.strip())


def commit_and_push(repo: Path, push: bool) -> None:
    tracked = [str(path) for path in SYNC_PATHS]
    run(["git", "add", "--", *tracked], repo)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    run(["git", "commit", "-m", f"Sync local case PDF OCR skill ({stamp})"], repo)
    if push:
        run(["git", "push", "origin", "main"], repo)


def main() -> int:
    args = parse_args()
    source = Path(args.source).expanduser().resolve()
    repo = Path(args.repo).expanduser().resolve()
    if args.push:
        args.commit = True
    if not (repo / ".git").exists():
        raise SystemExit(f"not a git repository: {repo}")

    require_clean_repo(repo, args.allow_dirty)
    if args.push and public_package_matches(source, repo):
        print("No public package changes to publish.")
        return 0
    if args.push:
        fast_forward_remote(repo)
    public_skill = sync_files(source, repo)
    if not args.no_validate:
        validate(public_skill, repo)
    if not changed(repo):
        print("No public package changes to publish.")
        return 0
    if args.commit:
        commit_and_push(repo, push=args.push)
        print("Synced, committed, and pushed." if args.push else "Synced and committed.")
    else:
        print("Synced local skill into public package. Review and commit when ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
