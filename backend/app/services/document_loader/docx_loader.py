from __future__ import annotations

import os
from pathlib import Path

from backend.app.services.segmenting.parser import detect_block_type
from backend.app.services.segmenting.models import DocumentBlock

from .exceptions import DocumentLoaderError


def load_docx_file(
    file_path: str | Path,
    doc_id: str = "",
    image_dir: str = "",
) -> list[DocumentBlock]:
    """读取 DOCX 文件。

    提取段落文本、表格文本，以及段落中内嵌的图片。
    """

    try:
        from docx import Document
        from docx.oxml.ns import qn
    except ImportError as exc:
        raise DocumentLoaderError(
            "读取 DOCX 需要安装 python-docx：pip install python-docx"
        ) from exc

    path = Path(file_path)
    document = Document(str(path))
    blocks: list[DocumentBlock] = []

    # 命名空间常量
    NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
    NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

    for index, paragraph in enumerate(document.paragraphs):
        text = paragraph.text.strip()

        # 抽取段落中的图片
        asset_refs = _extract_paragraph_images(
            paragraph, document, doc_id, image_dir, qn, NS_W, NS_A, NS_R
        )

        # 如果没有文本也没有图片，跳过空段落
        if not text and not asset_refs:
            continue

        # 图片专用的占位文本（必须在类型检测前设置，避免空文本导致报错）
        if not text and asset_refs:
            text = "[图片]"
            block_type = "image"
        else:
            block_type = _detect_docx_paragraph_type(paragraph.style.name, text)

        blocks.append(
            DocumentBlock(
                block_id=f"p{index:04d}",
                text=text,
                block_type=block_type,
                metadata={"style": paragraph.style.name},
                asset_refs=asset_refs,
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


def _extract_paragraph_images(
    paragraph: object,
    document: object,
    doc_id: str,
    image_dir: str,
    qn: object,
    NS_W: str,
    NS_A: str,
    NS_R: str,
) -> list[dict[str, str]]:
    """从段落中提取内嵌图片，保存到 image_dir，返回 asset_refs 列表。"""

    asset_refs: list[dict[str, str]] = []

    if not image_dir:
        return asset_refs

    for run in paragraph.runs:
        # 查找 w:drawing 元素（内嵌图片）
        drawings = run._element.findall(qn("w:drawing"))
        for drawing in drawings:
            # 查找 a:blip 元素（图片引用）
            blips = drawing.findall(".//" + qn("a:blip"))
            for blip in blips:
                embed = blip.get(qn("r:embed"))
                if not embed:
                    continue
                try:
                    image_part = document.part.related_parts[embed]
                except KeyError:
                    continue

                image_bytes = image_part.blob
                content_type = image_part.content_type or "image/png"
                ext = content_type.rsplit("/", 1)[-1]
                if ext == "jpeg":
                    ext = "jpg"

                # 生成唯一文件名
                filename = f"img_{embed[:8]}.{ext}"
                filepath = os.path.join(image_dir, filename)

                os.makedirs(image_dir, exist_ok=True)
                with open(filepath, "wb") as fh:
                    fh.write(image_bytes)

                asset_refs.append({
                    "type": "image",
                    "path": f"api/images/{doc_id}/{filename}",
                    "filename": filename,
                    "alt": "",
                })

    return asset_refs


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
