"""Baseline segmenters for RAG evaluation.

Provides two baselines:
- fixed_length: Uniform character-length chunks, no structure awareness.
- heading_based: Heading-boundary + length control, no semantic boundary.

Both are straw-man baselines that smart segmentation must outperform.
"""

from __future__ import annotations

from backend.app.services.segmenting.models import Chunk, SegmentConfig
from backend.app.services.segmenting.parser import parse_plain_text
from backend.app.services.segmenting.segmenter import segment_blocks


def fixed_length_segment(
    text: str,
    doc_id: str = "baseline",
    chunk_size: int = 512,
) -> list[Chunk]:
    """Split text into fixed-size chunks at the nearest sentence boundary.

    No structure awareness, no heading tracking, no overlap.
    This is the simplest straw-man baseline.

    Args:
        text: Input document text.
        doc_id: Document identifier for chunk IDs.
        chunk_size: Target character count per chunk (default 512).

    Returns:
        List of Chunk objects, same format as the smart segmenter.
    """
    if not text.strip():
        return []

    boundaries = _find_sentence_boundaries(text, chunk_size)

    chunks: list[Chunk] = []
    start = 0

    for index, boundary in enumerate(boundaries, start=1):
        content = text[start:boundary].strip()
        if not content:
            continue
        chunks.append(
            Chunk(
                chunk_id=f"{doc_id}_fixed_{index:04d}",
                content=content,
                title_path=[],
                chunk_type="normal",
                char_count=len(content),
                source_refs=[{"block_id": f"fixed_{start}_{boundary}"}],
                strategy_info={
                    "split_reason": "fixed_length",
                    "chunk_size": chunk_size,
                    "overlap": 0,
                },
                quality_flags=[],
            )
        )
        start = boundary

    return chunks


def heading_based_segment(
    text: str,
    doc_id: str = "heading_baseline",
    min_chars: int = 180,
    target_chars: int = 550,
    max_chars: int = 800,
) -> list[Chunk]:
    """Split text using heading boundaries + length control, WITHOUT semantic boundary.

    This baseline uses the same heading-detection and length-control logic
    as the smart segmenter, but disables semantic boundary detection and
    overlap. It answers the question: "How much does structure alone buy us?"

    Strategy name: "heading_only"

    Args:
        text: Input document text.
        doc_id: Document identifier for chunk IDs.
        min_chars: Minimum characters per chunk (shorter chunks get merged).
        target_chars: Target characters per chunk.
        max_chars: Maximum characters per chunk (longer chunks get split).

    Returns:
        List of Chunk objects, same format as the smart segmenter.
    """
    if not text.strip():
        return []

    config = SegmentConfig(
        min_chars=min_chars,
        target_chars=target_chars,
        max_chars=max_chars,
        overlap_sentences=0,                   # no overlap — clean baseline
        enable_semantic_boundary=False,         # structure only, no semantic
        heading_flush_min_chars=240,
    )

    blocks = parse_plain_text(text)
    result = segment_blocks(blocks, doc_id=doc_id, config=config)

    return result["chunks"]  # segment_blocks returns list[dict], compatible with eval_rag


def _find_sentence_boundaries(text: str, chunk_size: int) -> list[int]:
    """Find cut points at sentence boundaries nearest to chunk_size intervals."""
    boundaries: list[int] = []
    pos = 0
    text_len = len(text)

    while pos < text_len:
        target = pos + chunk_size
        if target >= text_len:
            boundaries.append(text_len)
            break

        window_end = min(target + chunk_size // 2, text_len)
        cut = target

        for i in range(target, window_end):
            if text[i] in "\n":
                cut = i + 1
                break
            if text[i] in ".!?。！？\n":
                cut = i + 1

        if cut == pos:
            cut = target

        boundaries.append(cut)
        pos = cut

    return boundaries
