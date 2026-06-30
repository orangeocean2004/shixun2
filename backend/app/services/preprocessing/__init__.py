"""Document preprocessing: cover/TOC removal, table flattening."""

from .cleaner import PreprocessReport, preprocess_document_blocks

__all__ = [
    "PreprocessReport",
    "preprocess_document_blocks",
]
