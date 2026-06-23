from __future__ import annotations

from pathlib import Path

from backend.app.services.segmenting.parser import parse_plain_text
from backend.app.services.segmenting.models import DocumentBlock


def load_text_file(file_path: str | Path) -> list[DocumentBlock]:
    """读取 TXT/Markdown 文件。

    文本类文件没有页码信息，所以只保留 block_id 和 block_type。
    """

    path = Path(file_path)
    text = read_text_with_fallback(path)
    return parse_plain_text(text)


def read_text_with_fallback(path: Path) -> str:
    """按常见中文文档编码顺序尝试读取文本。"""

    for encoding in ("utf-8", "utf-8-sig", "gb18030", "gbk"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")
