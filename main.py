"""
Simple Redfin Tagging Service - Single File Structure
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from contextlib import asynccontextmanager
import logging, logging.config, os, time, uuid
from typing import Callable

# ----- 로깅 설정 -----
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s %(levelname)s %(name)s: %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "access": {
            # uvicorn.access 가 추가하는 extra 필드 사용
            "format": '%(asctime)s %(levelname)s uvicorn.access: %(client_addr)s - "%(request_line)s" %(status_code)s',
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "default"},
        "access": {"class": "logging.StreamHandler", "formatter": "access"},
    },
    "loggers": {
        "": {"handlers": ["console"], "level": LOG_LEVEL},
        "uvicorn": {"level": LOG_LEVEL, "handlers": ["console"], "propagate": False},
        "uvicorn.error": {"level": LOG_LEVEL, "handlers": ["console"], "propagate": False},
        "uvicorn.access": {"level": LOG_LEVEL, "handlers": ["access"], "propagate": False},
        "redfin": {"level": LOG_LEVEL, "handlers": ["console"], "propagate": False},
    },
}
logging.config.dictConfig(LOGGING_CONFIG)
LOG = logging.getLogger("redfin.main")


# 시작/종료 이벤트
@asynccontextmanager
async def lifespan(app: FastAPI):
    LOG.info("=== Service starting ===")
    LOG.info("LOG_LEVEL=%s", LOG_LEVEL)
    try:
        yield
    finally:
        LOG.info("=== Service stopping ===")

# ----- FastAPI 앱 -----
from app.api import router
from app.routers.extract import router as extract_router
from app.routers.rss import router as rss_router
from app.routers.rec import router as rec_router

app = FastAPI(
    title="Redfin Tagging Service",
    description="Simple AI-powered tagging and categorization service",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 개발용, 프로덕션에서는 제한 필요
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 요청/응답 로깅 미들웨어
@app.middleware("http")
async def log_requests(request: Request, call_next: Callable):
    rid = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:12]
    start = time.perf_counter()
    client = request.client.host if request.client else "-"
    LOG.info(f"[{rid}] → {request.method} {request.url.path} from {client}")
    try:
        response = await call_next(request)
    except Exception as e:
        LOG.exception(f"[{rid}] 500 Internal Server Error")
        return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})
    dur_ms = (time.perf_counter() - start) * 1000
    LOG.info(f"[{rid}] ← {response.status_code} {request.url.path} ({dur_ms:.1f} ms)")
    # 응답 헤더에 request id 주입
    response.headers["X-Request-Id"] = rid
    return response

# Include unified API router
API_PREFIX = "/api/v1"
app.include_router(router, prefix=API_PREFIX)
app.include_router(extract_router, prefix=f"{API_PREFIX}/extract")
app.include_router(rss_router, prefix=f"{API_PREFIX}/rss")
app.include_router(rec_router, prefix=f"{API_PREFIX}/rec")

# Root endpoint
@app.get("/")
async def root():
    """루트 엔드포인트"""
    return {
        "service": "Redfin Tagging Service",
        "version": "0.1.0",
        "docs": "/docs",
        "health": f"{API_PREFIX}/health"
    }

if __name__ == "__main__":
    uvicorn.run(
        "main:app", 
        host="0.0.0.0", 
        port=8010, 
        reload=True
    )
