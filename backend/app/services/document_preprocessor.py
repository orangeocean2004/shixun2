from __future__ import annotations

import re
from dataclasses import dataclass

from backend.app.services.segmenting.models import DocumentBlock


TOC_PAGE_REF_PATTERNS = [
    re.compile(r"\t+\s*-?\s*\d+\s*-?\s*$"),
    re.compile(r"\.{2,}\s*\d+\s*$"),
    re.compile(r"\s+-\s*\d+\s*-\s*$"),
]

COVER_FIELD_PATTERN = re.compile(
    r"^(院（系）|院\(系\)|专业|班级|学号|姓名|带队教师|指导教师|日期|年\s*\d+\s*月|\d{4}\s*年)"
)


@dataclass
class PreprocessReport:
    original_count: int
    cleaned_count: int
    removed_cover_count: int = 0
    removed_toc_count: int = 0
    flattened_table_count: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "original_count": self.original_count,
            "cleaned_count": self.cleaned_count,
            "removed_cover_count": self.removed_cover_count,
            "removed_toc_count": self.removed_toc_count,
            "flattened_table_count": self.flattened_table_count,
        }


def preprocess_document_blocks(blocks: list[DocumentBlock]) -> tuple[list[DocumentBlock], PreprocessReport]:
    """Clean common Word report noise before chunking.

    This is intentionally conservative: it removes leading cover fields and
    table-of-contents entries, then flattens large one-cell body tables so the
    segmenter can split their text normally.
    """

    report = PreprocessReport(original_count=len(blocks), cleaned_count=0)
    cleaned: list[DocumentBlock] = []

    for index, block in enumerate(blocks):
        text = block.text.strip()
        if not text:
            continue

        if index < 24 and is_cover_block(text):
            report.removed_cover_count += 1
            continue

        if is_toc_marker(text) or is_toc_entry(text):
            report.removed_toc_count += 1
            continue

        if is_body_table(block):
            flattened = flatten_markdown_table(block.text)
            if flattened:
                cleaned.append(
                    DocumentBlock(
                        block_id=block.block_id,
                        text=flattened,
                        block_type="paragraph",
                        page=block.page,
                        metadata={
                            **block.metadata,
                            "preprocess": "flattened_body_table",
                            "original_block_type": block.block_type,
                        },
                    )
                )
                report.flattened_table_count += 1
                continue

        cleaned.append(block)

    report.cleaned_count = len(cleaned)
    return cleaned, report


def is_toc_marker(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    return compact in {"目录", "目錄"}


def is_toc_entry(text: str) -> bool:
    first_line = text.strip().splitlines()[0]
    return any(pattern.search(first_line) for pattern in TOC_PAGE_REF_PATTERNS)


def is_cover_block(text: str) -> bool:
    stripped = text.strip()
    compact = re.sub(r"\s+", "", stripped)
    if re.match(r"^(院（系）|院\(系\)|专业|班级|学号|姓名|带队教师|指导教师)[：:]", compact):
        return True
    if len(stripped) <= 24 and COVER_FIELD_PATTERN.match(stripped):
        return True
    if len(compact) <= 20 and re.match(r"^\d{4}年\d{1,2}月\d{1,2}日$", compact):
        return True
    if len(stripped) <= 36 and re.search(r"实习|实训|总结报告|课程设计", stripped):
        return True
    return False


def is_body_table(block: DocumentBlock) -> bool:
    if block.block_type != "table":
        return False
    text = block.text.strip()
    if len(text) < 1200:
        return False
    lines = [line for line in text.splitlines() if line.strip()]
    return len(lines) <= 6 or average_line_length(lines) > 240


def average_line_length(lines: list[str]) -> float:
    if not lines:
        return 0.0
    return sum(len(line) for line in lines) / len(lines)


def flatten_markdown_table(text: str) -> str:
    cells: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or is_markdown_separator_row(stripped):
            continue
        if "|" not in stripped:
            cells.append(stripped)
            continue
        parts = [part.strip() for part in stripped.strip("|").split("|")]
        cells.extend(part for part in parts if part)
    return "\n\n".join(cells).strip()


def is_markdown_separator_row(line: str) -> bool:
    stripped = line.strip().strip("|")
    if not stripped:
        return False
    cells = [cell.strip() for cell in stripped.split("|")]
    return all(re.fullmatch(r":?-{3,}:?", cell or "") for cell in cells)
