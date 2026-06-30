from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes import router
from backend.app.core.config import CORS_ALLOW_ORIGINS
from backend.app.services.model_settings import initialize_model_settings
from backend.app.services.rag_store.service import initialize_rag_store

app = FastAPI(title="RAG Smart Chunking API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    try:
        initialize_model_settings()
    except Exception:
        pass

    try:
        initialize_rag_store()
    except Exception:
        pass  # ChromaDB 初始化失败不影响分段功能


app.include_router(router)
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
