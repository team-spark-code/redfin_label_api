"""
Simple Redfin Tagging Service - Single File Structure
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app.api import router

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
app.include_router(router, prefix="/api/v1")

# Root endpoint
@app.get("/")
async def root():
    """루트 엔드포인트"""
    return {
        "service": "Redfin Tagging Service",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/api/v1/health"
    }

if __name__ == "__main__":
    uvicorn.run(
        "main:app", 
        host="0.0.0.0", 
        port=8010, 
        reload=True
    )
