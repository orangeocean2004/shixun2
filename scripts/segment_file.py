from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services.document_loader import load_document
from backend.app.services.segmenter import SegmentConfig, segment_blocks


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load a document file, segment it into chunks, and write JSON output."
    )
    parser.add_argument("input", help="Input file path, such as assets/title.md or assets/report.docx")
    parser.add_argument(
        "-o",
        "--output",
        help="Output JSON file path. Defaults to data/outputs/<input_stem>_chunks.json",
    )
    parser.add_argument("--doc-id", help="Document ID used as chunk_id prefix. Defaults to input file name.")
    parser.add_argument("--min-chars", type=int, default=300, help="Minimum chunk size in characters.")
    parser.add_argument("--target-chars", type=int, default=900, help="Preferred chunk size in characters.")
    parser.add_argument("--max-chars", type=int, default=1200, help="Maximum chunk size in characters.")
    parser.add_argument("--overlap-sentences", type=int, default=1, help="Sentence overlap when splitting long chunks.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else default_output_path(input_path)
    doc_id = args.doc_id or safe_doc_id(input_path.stem)

    config = SegmentConfig(
        min_chars=args.min_chars,
        target_chars=args.target_chars,
        max_chars=args.max_chars,
        overlap_sentences=args.overlap_sentences,
    )

    blocks = load_document(input_path)
    result = segment_blocks(blocks, doc_id=doc_id, config=config)
    result["source_file"] = str(input_path)
    result["block_count"] = len(blocks)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Loaded blocks: {len(blocks)}")
    print(f"Generated chunks: {result['statistics']['chunk_count']}")
    print(f"Output written: {output_path}")


def default_output_path(input_path: Path) -> Path:
    return PROJECT_ROOT / "data" / "outputs" / f"{safe_doc_id(input_path.stem)}_chunks.json"


def safe_doc_id(value: str) -> str:
    safe = "".join(char if char.isalnum() else "_" for char in value.strip())
    return safe.strip("_") or "doc"


if __name__ == "__main__":
    main()
