from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes import router
from backend.app.core.config import CORS_ALLOW_ORIGINS
from backend.app.core.model_settings import initialize_model_settings
from backend.app.services.rag_store.service import initialize_rag_store

logger = logging.getLogger(__name__)

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
    logger.info("startup: initializing model settings")
    try:
        initialize_model_settings()
        logger.info("startup: model settings initialized")
    except Exception:
        logger.exception("startup: failed to initialize model settings")

    logger.info("startup: initializing rag store")
    try:
        initialize_rag_store()
        logger.info("startup: rag store initialized")
    except Exception:
        logger.exception("startup: failed to initialize rag store")


app.include_router(router)
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
