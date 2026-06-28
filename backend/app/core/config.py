from pathlib import Path

ALLOWED_UPLOAD_SUFFIXES = {".txt", ".md", ".markdown", ".docx", ".pdf"}
DEFAULT_MIN_CHARS = 300
DEFAULT_TARGET_CHARS = 900
DEFAULT_MAX_CHARS = 1200
DEFAULT_OVERLAP_SENTENCES = 1
DEFAULT_RETRIEVE_TOP_K = 5
CORS_ALLOW_ORIGINS = ["http://127.0.0.1:5173", "http://localhost:5173"]

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
RAG_DIR = DATA_DIR / "rag"
SQLITE_DB_PATH = RAG_DIR / "rag_meta.db"
CHROMA_PERSIST_DIR = RAG_DIR / "chroma"
CHROMA_COLLECTION_NAME = "rag_chunks_v1"
