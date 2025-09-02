from __future__ import annotations
from dotenv import load_dotenv ; load_dotenv()
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel, Field

from ..models import TextIn, ExtractOut
from ..services.mongo_simple import MongoService

# 인스턴스 생성
mongo = MongoService()

from ..services.article_recom import ArticleService

# 인스턴스 생성
article_service = ArticleService(es_host='http://localhost:9200', es_auth=('elastic', 'elastic'), index_name='articles')

router = APIRouter(prefix="/v1/rec", tags=["recommend"])


# ---------- Schemas ----------
class IndexRequest(BaseModel):
    source_domain: Optional[str] = Field(None, description="해당 도메인만 인덱싱")
    reindex: bool = Field(False, description="기존 인덱스 재생성 여부")
    limit: int = Field(5000, ge=1, le=50000)

class SearchResponse(BaseModel):
    total: int
    items: List[Dict[str, Any]]


# ---------- Endpoints ----------
@router.post("/index")
def build_index(req: IndexRequest = Body(...), db = Depends(mongo.get_database)):
    es = article_service.es
    try:
        article_service.ensure_index(es, recreate=req.reindex)  # 없으면 만들고, 재색인 옵션 있으면 다시 만듦
        q: Dict[str, Any] = {}
        if req.source_domain:
            q["source"] = req.source_domain
        count = article_service.index_from_mongo(es=es, db=db, query=q, limit=req.limit)
        return {"indexed": count, "reindex": req.reindex, "filter": q}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"index error: {e!s}")


@router.post("/index")
def build_index(req: IndexRequest = Body(...), db = Depends(mongo.get_database)):
    es = article_service.es
    try:
        article_service.ensure_index(es, recreate=req.reindex)  # 없으면 만들고, 재색인 옵션 있으면 다시 만듦
        q: Dict[str, Any] = {}
        if req.source_domain:
            q["source"] = req.source_domain
        count = article_service.index_from_mongo(es=es, db=db, query=q, limit=req.limit)
        return {"indexed": count, "reindex": req.reindex, "filter": q}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"index error: {e!s}")

@router.get("/search")
def rec_search(q: str = Query(..., min_length=1, description="검색어"), size: int = Query(10, ge=1, le=100), offset: int = Query(0, ge=0)):
    es = article_service.es
    try:
        result = article_service.search_articles(es=es, query=q, size=size, offset=offset)
        return SearchResponse(total=result["total"], items=result["items"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"search error: {e!s}")
