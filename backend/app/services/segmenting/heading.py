from __future__ import annotations

import re


HEADING_PATTERNS = [
    re.compile(r"^(#{1,6})\s+(.+)$"),
    re.compile(r"^第[一二三四五六七八九十百千万\d]+[章节篇部分]\s*[：:、.]?\s*(.+)$"),
    re.compile(r"^[一二三四五六七八九十]+[、.]\s*(.+)$"),
    re.compile(r"^\d+(?:\.\d+){0,5}[、. ]\s*(.+)$"),
]


def is_heading(text: str) -> bool:
    """判断一个文本块是否像标题。

    标题通常较短，并且符合 Markdown、中文编号或数字编号格式。
    """

    first_line = text.strip().splitlines()[0]
    if len(first_line) > 80:
        return False
    return any(pattern.match(first_line) for pattern in HEADING_PATTERNS)


def heading_level(text: str) -> int:
    """估算标题层级，用于维护 title_path。

    例如：
    - # 标题 => 1
    - 1.2 标题 => 2
    - 一、标题 => 2
    """

    first_line = text.strip().splitlines()[0]
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
