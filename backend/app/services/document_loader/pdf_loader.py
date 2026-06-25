from __future__ import annotations

import os
import re
from pathlib import Path

from backend.app.services.segmenting.parser import detect_block_type, split_text_into_blocks
from backend.app.services.segmenting.models import DocumentBlock

from .exceptions import DocumentLoaderError


TEXT_SIGNAL_PATTERN = re.compile(r"[\w一-鿿]", re.UNICODE)


def load_pdf_file(
    file_path: str | Path,
    doc_id: str = "",
    image_dir: str = "",
) -> list[DocumentBlock]:
    """读取 PDF 文件。

    使用 PyMuPDF 按页抽取纯文本，再按空行拆成 block。
    同时提取页面中的内嵌图片。
    """

    try:
        import fitz
    except ImportError as exc:
        raise DocumentLoaderError("读取 PDF 需要安装 PyMuPDF：pip install pymupdf") from exc

    path = Path(file_path)
    document = fitz.open(str(path))
    blocks: list[DocumentBlock] = []

    for page_index, page in enumerate(document, start=1):
        text = page.get_text("text")
        page_blocks = split_text_into_blocks(text)

        # 提取该页的图片
        page_asset_refs = _extract_page_images(page, document, doc_id, image_dir, page_index)

        # 正常文本块
        text_blocks_in_page: list[DocumentBlock] = []
        for block_index, block_text in enumerate(page_blocks):
            block_text = block_text.strip()
            if not has_text_signal(block_text):
                continue
            text_blocks_in_page.append(
                DocumentBlock(
                    block_id=f"p{page_index:04d}_b{block_index:04d}",
                    text=block_text,
                    block_type=detect_block_type(block_text),
                    page=page_index,
                    metadata={"source": "pymupdf"},
                )
            )

        # 将图片附加到该页的第一个文本块；如果没有文本块，创建占位图片块
        if page_asset_refs:
            if text_blocks_in_page:
                text_blocks_in_page[0].asset_refs.extend(page_asset_refs)
            else:
                text_blocks_in_page.append(
                    DocumentBlock(
                        block_id=f"p{page_index:04d}_img",
                        text="[图片]",
                        block_type="image",
                        page=page_index,
                        metadata={"source": "pymupdf"},
                        asset_refs=page_asset_refs,
                    )
                )

        blocks.extend(text_blocks_in_page)

    document.close()
    return blocks


def _extract_page_images(
    page: object,
    document: object,
    doc_id: str,
    image_dir: str,
    page_index: int,
) -> list[dict[str, str]]:
    """从 PDF 页面提取内嵌图片，保存到 image_dir，返回 asset_refs 列表。"""

    asset_refs: list[dict[str, str]] = []

    if not image_dir:
        return asset_refs

    image_list = page.get_images(full=True)
    for img_idx, img_info in enumerate(image_list):
        xref = img_info[0]
        try:
            base_image = document.extract_image(xref)
        except Exception:
            continue

        image_bytes = base_image["image"]
        ext = base_image.get("ext", "png")

        filename = f"p{page_index:04d}_img{img_idx:04d}.{ext}"
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


def has_text_signal(text: str) -> bool:
    """过滤 PDF 抽取中的纯标点、纯符号噪声块。"""

    return bool(TEXT_SIGNAL_PATTERN.search(text))
