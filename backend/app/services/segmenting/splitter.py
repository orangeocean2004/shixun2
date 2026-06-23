from __future__ import annotations

import re
from typing import Any

from .heading import heading_level, normalize_heading
from .models import CandidateChunk, DocumentBlock, SegmentConfig


SENTENCE_PATTERN = re.compile(r"[^。！？!?；;.\n]+[。！？!?；;.]?")


def build_candidate_chunks(
    blocks: list[DocumentBlock],
    config: SegmentConfig,
) -> list[CandidateChunk]:
    """根据标题路径和目标长度生成候选 chunk。

    这一步不追求最终完美，而是先得到稳定、可解释的初始分段。
    """

    candidates: list[CandidateChunk] = []
    title_stack: list[tuple[int, str]] = []
    current_blocks: list[DocumentBlock] = []
    current_title_path: list[str] = []

    for block in blocks:
        # 标题本身不单独成为 chunk，而是作为后续内容的上下文。
        if block.block_type == "heading":
            if current_blocks:
                candidates.append(make_candidate(current_blocks, current_title_path, "heading_boundary"))
                current_blocks = []

            level = heading_level(block.text)
            title = normalize_heading(block.text)
            title_stack = [(item_level, item_title) for item_level, item_title in title_stack if item_level < level]
            title_stack.append((level, title))
            current_title_path = [item_title for _, item_title in title_stack]
            continue

        # 表格、公式、代码优先整体成块，避免破坏结构。
        if is_protected_block(block):
            if current_blocks:
                candidates.append(make_candidate(current_blocks, current_title_path, "before_special_block"))
                current_blocks = []
            candidates.append(make_candidate([block], current_title_path, f"protected_{block.block_type}"))
            continue

        current_blocks.append(block)
        if total_chars(current_blocks) >= config.target_chars:
            candidates.append(make_candidate(current_blocks, current_title_path, "target_length_reached"))
            current_blocks = []

    if current_blocks:
        candidates.append(make_candidate(current_blocks, current_title_path, "document_end"))

    return candidates


def split_oversized_chunks(
    candidates: list[CandidateChunk],
    config: SegmentConfig,
) -> list[CandidateChunk]:
    """把超长普通 chunk 按句子边界继续拆分。

    特殊块即使超长也先不强拆，只打 quality flag，避免破坏表格或代码。
    """

    result: list[CandidateChunk] = []
    for candidate in candidates:
        if len(candidate["content"]) <= config.max_chars or candidate["chunk_type"] in {"table", "formula", "code"}:
            result.append(candidate)
            continue

        pieces = split_long_text(candidate["content"], config)
        for index, piece in enumerate(pieces):
            split_candidate = dict(candidate)
            split_candidate["content"] = piece
            split_candidate["chunk_type"] = "normal"
            split_candidate["strategy_info"] = {
                **candidate["strategy_info"],
                "split_reason": "sentence_boundary_for_oversized_chunk",
                "split_index": index,
            }
            result.append(split_candidate)
    return result


def merge_short_chunks(
    candidates: list[CandidateChunk],
    config: SegmentConfig,
) -> list[CandidateChunk]:
    """合并过短 chunk。

    只合并同一个标题路径下的普通 chunk，避免跨章节混主题。
    """

    merged: list[CandidateChunk] = []
    index = 0

    while index < len(candidates):
        current = candidates[index]
        if (
            len(current["content"]) >= config.min_chars
            or current["chunk_type"] in {"table", "formula", "code"}
            or index + 1 >= len(candidates)
        ):
            merged.append(current)
            index += 1
            continue

        next_candidate = candidates[index + 1]
        can_merge = (
            current["title_path"] == next_candidate["title_path"]
            and next_candidate["chunk_type"] == "normal"
            and len(current["content"]) + len(next_candidate["content"]) <= config.max_chars
        )
        if not can_merge:
            merged.append(current)
            index += 1
            continue

        merged.append(merge_candidates(current, next_candidate))
        index += 2

    return merged


def is_protected_block(block: DocumentBlock) -> bool:
    """特殊结构块需要尽量整体保留。"""

    return block.block_type in {"table", "formula", "code"}


def make_candidate(
    blocks: list[DocumentBlock],
    title_path: list[str],
    split_reason: str,
) -> CandidateChunk:
    """把若干 DocumentBlock 打包成一个候选 chunk。"""

    content = "\n\n".join(block.text.strip() for block in blocks if block.text.strip())
    chunk_type = "normal"
    if len(blocks) == 1 and is_protected_block(blocks[0]):
        chunk_type = blocks[0].block_type

    return {
        "content": content,
        "title_path": list(title_path),
        "chunk_type": chunk_type,
        "source_blocks": list(blocks),
        "strategy_info": {"split_reason": split_reason},
    }


def split_long_text(text: str, config: SegmentConfig) -> list[str]:
    """按句子切分超长文本，并给后续 chunk 添加少量句子 overlap。"""

    sentences = split_sentences(text)
    pieces: list[str] = []
    current: list[str] = []

    for sentence in sentences:
        if current and len("".join(current)) + len(sentence) > config.max_chars:
            pieces.append("".join(current).strip())
            overlap = current[-config.overlap_sentences :] if config.overlap_sentences > 0 else []
            current = list(overlap)
        current.append(sentence)

    if current:
        pieces.append("".join(current).strip())

    return [piece for piece in pieces if piece]


def split_sentences(text: str) -> list[str]:
    """中英文常见句末标点切句。"""

    sentences = [match.group(0).strip() for match in SENTENCE_PATTERN.finditer(text) if match.group(0).strip()]
    return sentences or [text.strip()]


def merge_candidates(left: CandidateChunk, right: CandidateChunk) -> CandidateChunk:
    """合并两个候选 chunk，并记录合并原因。"""

    return {
        "content": f'{left["content"]}\n\n{right["content"]}'.strip(),
        "title_path": left["title_path"],
        "chunk_type": "normal",
        "source_blocks": left["source_blocks"] + right["source_blocks"],
        "strategy_info": {
            "split_reason": right["strategy_info"].get("split_reason", "merged"),
            "merge_reason": "short_chunk_same_title_path",
        },
    }


def total_chars(blocks: list[DocumentBlock]) -> int:
    """统计多个块的字符数，当前作为 token 数的近似。"""

    return sum(len(block.text) for block in blocks)
