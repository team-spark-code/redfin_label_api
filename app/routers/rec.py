from __future__ import annotations
import os
from dotenv import load_dotenv; load_dotenv()
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel, Field

from ..services.mongo_simple import MongoService
from ..services.article_recom import ArticleService

# Services
mongo = MongoService()
article_service = ArticleService(
    es_host=os.getenv("ES_HOST", "http://localhost:9200"),
    es_auth=(os.getenv("ES_USER", "elastic"), os.getenv("ES_PASSWORD", "elastic")),
    index_name=os.getenv("INDEX_NAME", "article_recommender")
)

router = APIRouter(prefix="/v1/rec", tags=["recommend"])

# ---------- Schemas ----------
class IndexRequest(BaseModel):
    reindex: bool = Field(False, description="기존 인덱스 재생성 여부")
    file_path: Optional[str] = Field(None, description="JSON/JSONL 파일 경로")
    limit: int = Field(5000, ge=1, le=50000)

class SearchResponse(BaseModel):
    total: int
    items: List[Dict[str, Any]]


# ---------- Endpoints ----------
@router.post("/index")
def build_index(req: IndexRequest = Body(...)):
    try:
        if req.reindex:
            article_service.create_index()

        if not req.file_path:
            raise HTTPException(status_code=400, detail="file_path is required")

        articles = article_service.load_jsonl_data(req.file_path)
        if req.limit:
            articles = articles[:req.limit]

        count = article_service.index_articles(articles)
        return {"indexed": count, "reindex": req.reindex}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"index error: {e!s}")


@router.get("/search")
def rec_search(
    q: str = Query(..., min_length=1, description="검색어"),
    size: int = Query(10, ge=1, le=100)
):
    try:
        results = article_service.search_recommendations(query=q, top_k=size)
        return SearchResponse(total=len(results), items=results)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"search error: {e!s}")
