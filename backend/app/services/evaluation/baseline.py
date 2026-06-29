"""Fixed-length baseline segmenter for RAG evaluation.

Produces chunks of uniform character length with no overlap,
no structure awareness, no heading tracking. This is the
straw-man baseline that smart segmentation must outperform.
"""

from __future__ import annotations

from backend.app.services.segmenting.models import Chunk


def fixed_length_segment(
    text: str,
    doc_id: str = "baseline",
    chunk_size: int = 512,
) -> list[Chunk]:
    """Split text into fixed-size chunks at the nearest sentence boundary.

    Args:
        text: Input document text.
        doc_id: Document identifier for chunk IDs.
        chunk_size: Target character count per chunk (default 512).

    Returns:
        List of Chunk objects, same format as the smart segmenter.
    """
    if not text.strip():
        return []

    # Find sentence boundaries
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

        # Search for the nearest sentence boundary after target
        # Look within a window of chunk_size//2 after target
        window_end = min(target + chunk_size // 2, text_len)
        cut = target

        for i in range(target, window_end):
            if text[i] in "\n":
                # Prefer paragraph breaks
                cut = i + 1
                break
            if text[i] in ".!?。！？\n":
                cut = i + 1

        if cut == pos:  # No boundary found, force cut
            cut = target

        boundaries.append(cut)
        pos = cut

    return boundaries
