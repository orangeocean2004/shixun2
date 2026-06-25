"""RAG evaluation framework.

    Baseline segmenter (baseline):    Fixed-length chunking for comparison.
    Metrics (metrics):                IR metrics + semantic relevance judge.
"""

from .baseline import fixed_length_segment
from .metrics import EmbeddingRelevance, compute_ir_metrics, run_segmenter_comparison

__all__ = [
    "EmbeddingRelevance",
    "compute_ir_metrics",
    "fixed_length_segment",
    "run_segmenter_comparison",
]
