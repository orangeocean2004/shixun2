from __future__ import annotations

from pathlib import Path

from backend.app.services.segmenting.models import DocumentBlock

from .docx_loader import load_docx_file
from .exceptions import DocumentLoaderError
from .pdf_loader import load_pdf_file
from .text_loader import load_text_file


def load_document(file_path: str | Path, doc_id: str | None = None) -> list[DocumentBlock]:
    """按文件后缀分发到对应读取器。

    返回值统一是 DocumentBlock 列表，后续直接交给 segment_blocks。
    doc_id 用于图片提取时的存储目录名。
    """

    path = Path(file_path)
    suffix = path.suffix.lower()

    if not path.exists():
        raise DocumentLoaderError(f"文件不存在：{path}")

    if suffix in {".txt", ".md", ".markdown"}:
        return load_text_file(path)
    if suffix == ".docx":
        return load_docx_file(path, doc_id=doc_id)
    if suffix == ".pdf":
        return load_pdf_file(path)

    raise DocumentLoaderError(f"暂不支持的文件类型：{suffix or '无后缀'}")
