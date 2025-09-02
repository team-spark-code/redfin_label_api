"""
Simple Redfin Tagging Service - Single File Structure
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

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
