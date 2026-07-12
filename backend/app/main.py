from __future__ import annotations

import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes import router
from backend.app.core.config import CORS_ALLOW_ORIGINS
from backend.app.core.model_settings import initialize_model_settings
from backend.app.services.rag_store.service import initialize_rag_store

logger = logging.getLogger(__name__)
request_logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="RAG Smart Chunking API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_http_request(request: Request, call_next):
    start = time.perf_counter()
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        client_ip = forwarded_for.split(",", 1)[0].strip()
    else:
        client_ip = request.client.host if request.client else "-"

    logger.info(
        "[http::request] start method=%s path=%s client_ip=%s",
        request.method,
        request.url.path,
        client_ip,
    )

    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        cost_ms = (time.perf_counter() - start) * 1000
        request_logger.info(
            "[http::request] end method=%s path=%s status=%s cost=%.2fms client_ip=%s",
            request.method,
            request.url.path,
            status_code,
            cost_ms,
            client_ip,
        )


@app.on_event("startup")
def on_startup() -> None:
    logger.info("startup: initializing model settings")
    initialize_model_settings()
    logger.info("startup: model settings initialized")

    logger.info("startup: initializing rag store (SQLite + ChromaDB)")
    initialize_rag_store()
    logger.info("startup: rag store ready")


app.include_router(router)
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
