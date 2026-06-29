from __future__ import annotations

import re


HEADING_PATTERNS = [
    re.compile(r"^(#{1,6})\s+(.+)$"),
    re.compile(r"^第[一二三四五六七八九十百千万\d]+[章节篇部分]\s*[：:、.]?\s*(.+)$"),
    re.compile(r"^[一二三四五六七八九十]+[、.]\s*(.+)$"),
    re.compile(r"^\d+(?:\.\d+){0,5}[、. ]\s*(.+)$"),
]

# 常见英文学术标题关键词（单独成行时视为标题）
_ENGLISH_HEADING_KEYWORDS = frozenset({
    "abstract", "keywords", "contents", "references", "acknowledgments",
    "acknowledgements", "introduction", "conclusion", "appendix", "summary",
    "background", "methodology", "methods", "results", "discussion",
    "related work", "future work", "bibliography",
})

TOC_PAGE_REF_PATTERNS = [
    re.compile(r"\t+\s*-?\s*\d+\s*-?\s*$"),
    re.compile(r"\.{2,}\s*\d+\s*$"),
    re.compile(r"\s+-\s*\d+\s*-\s*$"),
]


def is_heading(text: str) -> bool:
    """判断一个文本块是否像标题。

    标题通常较短，并且符合 Markdown、中文编号或数字编号格式。
    也识别常见英文学术标题（Abstract、Keywords 等）单独成行的情况。
    """

    first_line = text.strip().splitlines()[0]
    if len(first_line) > 80:
        return False
    if looks_like_toc_entry(first_line):
        return False

    # 常见英文学术标题单独成行
    if first_line.lower() in _ENGLISH_HEADING_KEYWORDS:
        return True

    return any(pattern.match(first_line) for pattern in HEADING_PATTERNS)


def looks_like_toc_entry(text: str) -> bool:
    """Reject table-of-contents rows such as '1. Intro    - 4 -'."""

    return any(pattern.search(text.strip()) for pattern in TOC_PAGE_REF_PATTERNS)


def heading_level(text: str) -> int:
    """估算标题层级，用于维护 title_path。

    例如：
    - # 标题 => 1
    - 1.2 标题 => 2
    - 一、标题 => 2
    - Abstract => 1（英文学术标题视为一级）
    """

    first_line = text.strip().splitlines()[0]

    if first_line.lower() in _ENGLISH_HEADING_KEYWORDS:
        return 1

    markdown_match = HEADING_PATTERNS[0].match(first_line)
    if markdown_match:
        return len(markdown_match.group(1))
    if first_line.startswith("第"):
        return 1
    if re.match(r"^[一二三四五六七八九十]+[、.]", first_line):
        return 2
    number_match = re.match(r"^(\d+(?:\.\d+)*)", first_line)
    if number_match:
        return number_match.group(1).count(".") + 1
    return 3


def normalize_heading(text: str) -> str:
    """把标题行整理成可展示的标题文本。"""

    return text.strip().splitlines()[0].strip("# ").strip()
