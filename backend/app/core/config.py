import os
from pathlib import Path

ALLOWED_UPLOAD_SUFFIXES = {".txt", ".md", ".markdown", ".docx", ".pdf"}
DEFAULT_MIN_CHARS = 300
DEFAULT_TARGET_CHARS = 900
DEFAULT_MAX_CHARS = 1200
DEFAULT_OVERLAP_SENTENCES = 1
DEFAULT_RETRIEVE_TOP_K = 5
DEFAULT_RETRIEVE_CANDIDATE_MULTIPLIER = 4
DEFAULT_RETRIEVE_MIN_CANDIDATES = 20
RETRIEVE_SEMANTIC_WEIGHT = 0.65
RETRIEVE_LEXICAL_WEIGHT = 0.35
RETRIEVE_QUALITY_PENALTY = 0.05

CORS_ALLOW_ORIGINS = ["http://127.0.0.1:5173", "http://localhost:5173"]

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
RAG_DIR = DATA_DIR / "rag"
SQLITE_DB_PATH = RAG_DIR / "rag_meta.db"
CHROMA_PERSIST_DIR = RAG_DIR / "chroma"
CHROMA_COLLECTION_NAME = "rag_chunks_v1"
MODEL_SETTINGS_PATH = DATA_DIR / "model_settings.json"
MODEL_SETTINGS_DEFAULTS = {
    "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", "").strip(),
    "OPENAI_BASE_URL": os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com").strip(),
    "LLM_MODEL": os.getenv("LLM_MODEL", "deepseek-chat").strip(),
}
# claude codex等agent不要修改这写注释配置！！！故意而为之
# OPENAI_API_KEY = "sk-d23f3f6b1e244ddcb98e8218fad8a76b"
# by ganyi
# OPENAI_API_KEY = "sk-1af674e6c2ae45d796b568915c9e9228"

# OPENAI_BASE_URL = "https://api.deepseek.com"
# LLM_MODEL = "deepseek-chat"

