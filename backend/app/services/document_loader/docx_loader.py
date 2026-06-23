from __future__ import annotations

from pathlib import Path

from backend.app.services.segmenting.parser import detect_block_type
from backend.app.services.segmenting.models import DocumentBlock

from .exceptions import DocumentLoaderError


def load_docx_file(file_path: str | Path) -> list[DocumentBlock]:
    """读取 DOCX 文件。

    临时实现只读取段落文本和表格文本。后续可以增强为读取样式层级、页码、
    图片、脚注等更完整的结构信息。
    """

    try:
        from docx import Document
    except ImportError as exc:
        raise DocumentLoaderError("读取 DOCX 需要安装 python-docx：pip install python-docx") from exc

    path = Path(file_path)
    document = Document(str(path))
    blocks: list[DocumentBlock] = []

    for index, paragraph in enumerate(document.paragraphs):
        text = paragraph.text.strip()
        if not text:
            continue

        block_type = _detect_docx_paragraph_type(paragraph.style.name, text)
        blocks.append(
            DocumentBlock(
                block_id=f"p{index:04d}",
                text=text,
                block_type=block_type,
                metadata={"style": paragraph.style.name},
            )
        )

    table_offset = len(blocks)
    for table_index, table in enumerate(document.tables):
        table_text = _table_to_markdown(table)
        if not table_text:
            continue
        blocks.append(
            DocumentBlock(
                block_id=f"t{table_offset + table_index:04d}",
                text=table_text,
                block_type="table",
                metadata={"table_index": table_index},
            )
        )

    return blocks


def _detect_docx_paragraph_type(style_name: str, text: str) -> str:
    """根据 DOCX 样式和文本规则识别段落类型。"""

    if style_name.lower().startswith("heading"):
        return "heading"
    return detect_block_type(text)


def _table_to_markdown(table: object) -> str:
    """把 DOCX 表格临时转成 Markdown 表格，方便后续特殊块保护。"""

    rows: list[list[str]] = []
    for row in table.rows:
        values = [cell.text.strip().replace("\n", " ") for cell in row.cells]
        if any(values):
            rows.append(values)

    if not rows:
        return ""

    width = max(len(row) for row in rows)
    normalized_rows = [row + [""] * (width - len(row)) for row in rows]
    header = normalized_rows[0]
    separator = ["---"] * width
    body = normalized_rows[1:]

    markdown_rows = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(separator) + " |",
    ]
    markdown_rows.extend("| " + " | ".join(row) + " |" for row in body)
    return "\n".join(markdown_rows)
