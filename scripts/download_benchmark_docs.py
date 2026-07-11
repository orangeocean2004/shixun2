# -*- coding: utf-8 -*-
"""Download public Chinese documents for building a diverse self-built eval dataset.

Document types targeted:
  - Technical manuals (multi-chapter, structured headings)
  - Tutorials/guides (code blocks, lists, tables)
  - White papers/reports (structured sections, data tables)
  - Standards/specifications (formal structure, formulas)

Output: data/benchmarks/docs/zh/*.txt (UTF-8 plain text)

Usage:
    python scripts/download_benchmark_docs.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "data" / "benchmarks" / "docs" / "zh"

# ── Candidate documents ──────────────────────────────────────────
# Each entry: (filename, url, description)
CANDIDATES: list[tuple[str, str, str]] = [
    # ── GitHub raw Markdown: well-structured Chinese technical docs ──
    (
        "vue3_guide_intro.txt",
        "https://raw.githubusercontent.com/vuejs-translations/docs-zh-cn/main/src/guide/introduction.md",
        "Vue3 中文官方文档 — 简介章节（标题层级、代码块、列表）",
    ),
    (
        "vue3_guide_essentials.txt",
        "https://raw.githubusercontent.com/vuejs-translations/docs-zh-cn/main/src/guide/essentials/reactivity-fundamentals.md",
        "Vue3 中文官方文档 — 响应式基础（多级标题、代码示例、API表格）",
    ),
    # ── Rust 中文教程 ──
    (
        "rust_zh_ownership.txt",
        "https://raw.githubusercontent.com/rust-lang-cn/book-cn/master/src/ch04-01-what-is-ownership.md",
        "Rust 中文教程 — 所有权章节（结构化、代码块、概念解释）",
    ),
    (
        "rust_zh_structs.txt",
        "https://raw.githubusercontent.com/rust-lang-cn/book-cn/master/src/ch05-01-defining-structs.md",
        "Rust 中文教程 — 结构体章节（代码示例、表格、多级标题）",
    ),
    # ── Python 教程 ──
    (
        "python_cn_classes.txt",
        "https://raw.githubusercontent.com/Prodesire/Python-Guide-CN/master/docs/python/classes.rst",
        "Python 中文指南 — 类章节",
    ),
    # ── 政府/公开报告（尝试多个来源）──
    # ── 学术论文摘要 ──
    # ── 开源项目文档 ──
    (
        "react_zh_quickstart.txt",
        "https://raw.githubusercontent.com/reactjs/zh-hans.react.dev/main/src/content/learn/index.md",
        "React 中文文档 — 快速开始（结构化、代码示例）",
    ),
    (
        "flutter_cn_intro.txt",
        "https://raw.githubusercontent.com/cfug/flutter.cn/master/src/docs/get-started/install/windows.md",
        "Flutter 中文文档 — 安装指南（步骤列表、代码块、表格）",
    ),
]

# ── Also try arxiv papers (convert from PDF would need extra deps, skip for now) ──

HEADERS = {
    "User-Agent": "Mozilla/5.0 (benchmark-doc-downloader research-use-only)",
}


def download(url: str, dest: Path, desc: str) -> bool:
    """Download a single file. Returns True on success."""
    if dest.exists():
        print(f"  SKIP (exists): {dest.name}")
        return True

    try:
        req = Request(url, headers=HEADERS)
        with urlopen(req, timeout=30) as resp:
            if resp.status != 200:
                print(f"  FAIL HTTP {resp.status}: {desc[:60]}")
                return False
            raw = resp.read()
    except (HTTPError, URLError, OSError) as e:
        print(f"  FAIL {type(e).__name__}: {desc[:60]}")
        return False

    # Try UTF-8 decode
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = raw.decode("gbk")
        except UnicodeDecodeError:
            text = raw.decode("utf-8", errors="replace")

    # Strip frontmatter (YAML --- blocks) and clean up
    lines = text.splitlines()
    cleaned: list[str] = []

    # If file starts with ---, skip YAML frontmatter
    skip_frontmatter = lines and lines[0].strip() == "---"
    fm_closed = False
    for line in lines:
        if skip_frontmatter and not fm_closed:
            if line.strip() == "---" and cleaned:
                fm_closed = True
            continue
        cleaned.append(line)

    # Remove empty leading lines
    while cleaned and not cleaned[0].strip():
        cleaned.pop(0)

    output = "\n".join(cleaned).strip()
    if len(output) < 500:
        print(f"  WARN too short ({len(output)} chars): {desc[:60]}")
        return False

    dest.write_text(output, encoding="utf-8")
    print(f"  OK  {dest.name}  ({len(output):,} chars) — {desc[:60]}")
    return True


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Output dir: {OUTPUT_DIR}")
    print(f"Attempting {len(CANDIDATES)} documents...\n")

    ok = 0
    for filename, url, desc in CANDIDATES:
        dest = OUTPUT_DIR / filename
        print(f"[{desc[:60]}]")
        if download(url, dest, desc):
            ok += 1
        time.sleep(0.5)  # be polite

    print(f"\n{'='*60}")
    print(f"Downloaded: {ok}/{len(CANDIDATES)}")
    print(f"Output dir: {OUTPUT_DIR}")

    # List all downloaded files
    existing = sorted(OUTPUT_DIR.glob("*.txt"))
    if existing:
        print(f"\nFiles in dataset ({len(existing)}):")
        for f in existing:
            size_kb = f.stat().st_size / 1024
            print(f"  {f.name:40s}  {size_kb:6.1f} KB")


if __name__ == "__main__":
    main()
