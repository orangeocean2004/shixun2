from __future__ import annotations

from pathlib import Path
import re

from backend.app.services.segmenting.parser import detect_block_type, split_text_into_blocks
from backend.app.services.segmenting.models import DocumentBlock

from .exceptions import DocumentLoaderError


TEXT_SIGNAL_PATTERN = re.compile(r"[\w\u4e00-\u9fff]", re.UNICODE)


def load_pdf_file(file_path: str | Path) -> list[DocumentBlock]:
    """读取 PDF 文件。

    临时实现使用 PyMuPDF 按页抽取纯文本，再按空行拆成 block。
    复杂 PDF 的表格、公式和版面顺序后续需要接更专业的解析器增强。
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

        for block_index, block_text in enumerate(page_blocks):
            block_text = block_text.strip()
            if not has_text_signal(block_text):
                continue
            blocks.append(
                DocumentBlock(
                    block_id=f"p{page_index:04d}_b{block_index:04d}",
                    text=block_text,
                    block_type=detect_block_type(block_text),
                    page=page_index,
                    metadata={"source": "pymupdf"},
                )
            )

    document.close()
    return blocks


def has_text_signal(text: str) -> bool:
    """过滤 PDF 抽取中的纯标点、纯符号噪声块。"""

    return bool(TEXT_SIGNAL_PATTERN.search(text))
