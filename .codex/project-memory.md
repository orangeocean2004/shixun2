# Project Memory

## Project

This is a course project for "面向 RAG 的智能分段与内容组织智能体".

Goal: build a Vue + FastAPI + Python service that loads documents, segments them into RAG-ready chunks, enriches chunks later with summaries/tags/entities, and evaluates against fixed-length baselines.

## Current Architecture

- Frontend: Vue planned under `frontend/`.
- Backend: FastAPI planned under `backend/`.
- Business logic: Python modules under `backend/app/services/`.
- Current runnable CLI test: `scripts/segment_file.py`.

## Implemented Modules

- `backend/app/services/segmenting/`
  - `models.py`: `SegmentConfig`, `DocumentBlock`, `Chunk`.
  - `parser.py`: converts plain text into `DocumentBlock` objects. It now supports line-level parsing, Chinese numbered headings, bullet markers, Markdown table grouping, and formula detection.
  - `heading.py`: heading detection and heading-level estimation.
  - `splitter.py`: candidate chunk generation, protected table/formula/code blocks, oversized chunk splitting, short chunk merging.
  - `statistics.py`: chunk statistics and JSON conversion.
  - `segmenter.py`: main `segment_text()` and `segment_blocks()` entry points.
- `backend/app/services/segmenter.py`
  - Compatibility re-export for old imports.
- `backend/app/services/document_loader/`
  - `loader.py`: dispatches by file extension.
  - `text_loader.py`: txt/md reader with encoding fallback.
  - `docx_loader.py`: temporary DOCX paragraph/table reader using `python-docx`.
  - `pdf_loader.py`: temporary PDF text reader using `PyMuPDF`.

## Current Test Command

```powershell
python scripts\segment_file.py assets\title.md -o data\outputs\title_chunks.json --min-chars 200 --target-chars 800 --max-chars 1200
```

Latest observed result for `assets/title.md`:

- Loaded blocks: 24
- Generated chunks: 8
- Output: `data/outputs/title_chunks.json`

## Current Quality

The segmenter is now a usable structure-aware prototype, not final production quality.

Good:

- Recognizes Chinese section headings like `一、课题背景`.
- Produces `title_path`.
- Protects table/formula/code blocks.
- Emits `source_refs`, `strategy_info`, `quality_flags`, and statistics.

Needs improvement:

- Detect document-level main title better.
- Add `content_with_context` so RAG retrieval sees heading context.
- Improve short-section merge strategy.
- Replace char count with tokenizer-based token count later.
- Add fixed-length baseline and retrieval evaluation.
- Add organizer module for summary/keywords/tags.
- Add FastAPI `/segment` endpoint.

## Next Recommended Step

Add `content_with_context` to every chunk:

- Keep raw `content`.
- Add `content_with_context = title_path joined + content`.
- Use this for future embedding/RAG retrieval.

