"""RAG evaluation framework.

    Baseline segmenters (baseline):   Fixed-length + heading-based chunking.
    Metrics (metrics):                IR metrics + semantic relevance judge.
"""

from .baseline import fixed_length_segment, heading_based_segment
from .metrics import EmbeddingRelevance, compute_ir_metrics, run_segmenter_comparison

__all__ = [
    "EmbeddingRelevance",
    "compute_ir_metrics",
    "fixed_length_segment",
    "heading_based_segment",
    "run_segmenter_comparison",
]
