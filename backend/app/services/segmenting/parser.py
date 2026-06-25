from __future__ import annotations

import re
from pathlib import Path

from .heading import is_heading
from .models import DocumentBlock


# ── Asset reference detection ─────────────────────────────

_ASSET_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp",
    ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt",
    ".zip", ".tar", ".gz", ".7z",
    ".py", ".json", ".yaml", ".yml", ".csv", ".sql",
}

_MD_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_MD_LINK = re.compile(r"(?<!!)\[([^\]]*)\]\(([^)]+)\)")


def extract_asset_refs(text: str) -> list[dict[str, str]]:
    """从文本中提取外置资产引用（图片/附件/文件链接）。

    只识别两类 Markdown 语法：
    - 图片：``![alt](path)``
    - 文件链接：``[text](path)``（path 指向已知扩展名或相对路径）
    """
    refs: list[dict[str, str]] = []
    seen: set[str] = set()

    for match in _MD_IMAGE.finditer(text):
        alt = match.group(1).strip()
        path = match.group(2).strip()
        if path not in seen and _is_local_asset(path):
            seen.add(path)
            refs.append({"type": "image", "path": path, "alt": alt})

    for match in _MD_LINK.finditer(text):
        label = match.group(1).strip()
        path = match.group(2).strip()
        if path not in seen and _is_local_asset(path):
            seen.add(path)
            label_lower = label.lower()
            if any(kw in label_lower for kw in ("图", "表", "fig", "table", "附件", "attached")):
                refs.append({"type": "attachment", "path": path, "label": label})

    return refs


def _is_local_asset(path: str) -> bool:
    """判断路径是否为本地资产引用（非 http URL）。"""
    if path.startswith(("http://", "https://", "mailto:", "#")):
        return False
    suffix = Path(path).suffix.lower()
    if suffix in _ASSET_EXTENSIONS:
        return True
    # 无扩展名但路径像是文件路径的，也认定为资产
    if "/" in path or "\\" in path:
        return bool(suffix)  # 有路径分隔符且有扩展名
    return False


def parse_plain_text(text: str) -> list[DocumentBlock]:
    """把纯文本解析成 DocumentBlock 列表。

    这里先用空行分块，适合课程项目早期演示。后续如果接 DOCX/PDF 解析器，
    可以绕过这个函数，直接传入结构化 DocumentBlock。
    """

    blocks: list[DocumentBlock] = []
    in_code = False
    code_lines: list[str] = []
    code_start_index = 0

    raw_blocks = split_text_into_blocks(text)
    for raw_index, raw_block in enumerate(raw_blocks):
        block = raw_block.strip()
        if not block:
            continue

        # 三反引号代码块需要整体保留，避免把代码从中间切断。
        if block.startswith("```"):
            in_code = True
            code_lines = [block]
            code_start_index = raw_index
            continue

        if in_code:
            code_lines.append(block)
            if block.endswith("```"):
                blocks.append(
                    DocumentBlock(
                        block_id=f"b{code_start_index:04d}",
                        text="\n\n".join(code_lines),
                        block_type="code",
                    )
                )
                in_code = False
                code_lines = []
            continue

        block_type = detect_block_type(block)
        blocks.append(
            DocumentBlock(
                block_id=f"b{raw_index:04d}",
                text=block,
                block_type=block_type,
                asset_refs=extract_asset_refs(block),
            )
        )

    if code_lines:
        blocks.append(
            DocumentBlock(
                block_id=f"b{code_start_index:04d}",
                text="\n\n".join(code_lines),
                block_type="code",
            )
        )

    return blocks


def split_text_into_blocks(text: str) -> list[str]:
    """把原始纯文本拆成更细的逻辑块。

    很多 PDF/Word 转出来的文本不是用空行分段，而是每一行代表标题、段落
    或项目符号。这里先做一层行级归并，让后续分段能真正看到文档结构。
    """

    blocks: list[str] = []
    paragraph_lines: list[str] = []
    table_lines: list[str] = []
    pending_bullet = ""

    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            flush_table(table_lines, blocks)
            flush_paragraph(paragraph_lines, blocks)
            pending_bullet = ""
            continue

        if is_heading(line):
            flush_table(table_lines, blocks)
            flush_paragraph(paragraph_lines, blocks)
            blocks.append(line)
            pending_bullet = ""
            continue

        if looks_like_table_line(line):
            flush_paragraph(paragraph_lines, blocks)
            table_lines.append(line)
            pending_bullet = ""
            continue

        if table_lines:
            flush_table(table_lines, blocks)

        if is_bullet_marker(line):
            flush_paragraph(paragraph_lines, blocks)
            pending_bullet = line
            continue

        if starts_with_bullet(line):
            flush_paragraph(paragraph_lines, blocks)
            blocks.append(line)
            pending_bullet = ""
            continue

        if pending_bullet:
            blocks.append(f"{pending_bullet} {line}".strip())
            pending_bullet = ""
            continue

        paragraph_lines.append(line)

    flush_table(table_lines, blocks)
    flush_paragraph(paragraph_lines, blocks)
    return blocks


def flush_paragraph(lines: list[str], blocks: list[str]) -> None:
    """提交当前普通段落。"""

    if lines:
        blocks.append("\n".join(lines))
        lines.clear()


def flush_table(lines: list[str], blocks: list[str]) -> None:
    """提交当前表格块。"""

    if lines:
        blocks.append("\n".join(lines))
        lines.clear()


def starts_with_bullet(line: str) -> bool:
    """识别带内容的项目符号。"""

    return bool(re.match(r"^[•*-]\s*\S+", line))


def is_bullet_marker(line: str) -> bool:
    """识别单独一行的项目符号，下一行会和它合并。"""

    return line in {"•", "-", "*"}


def looks_like_table_line(line: str) -> bool:
    """识别 Markdown 表格的一行。"""

    return "|" in line and line.count("|") >= 2


def detect_block_type(text: str) -> str:
    """识别文本块类型。

    先区分标题、表格、公式、代码和普通段落，分段时会对特殊块做保护。
    """

    if is_heading(text):
        return "heading"
    if looks_like_table(text):
        return "table"
    if text.startswith("```") or text.endswith("```"):
        return "code"
    if looks_like_formula(text):
        return "formula"
    return "paragraph"


def looks_like_table(text: str) -> bool:
    """粗略识别 Markdown 表格。"""

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    pipe_lines = [line for line in lines if "|" in line]
    return len(pipe_lines) >= 2


def looks_like_formula(text: str) -> bool:
    """粗略识别短公式块。"""

    stripped = text.strip()
    if stripped.startswith("$$") and stripped.endswith("$$"):
        return True
    if "\n" in stripped or len(stripped) > 160:
        return False
    return bool(re.search(r"[=≈≤≥]\s*[\w\d({\[]", stripped))
