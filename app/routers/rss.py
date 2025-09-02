# app/routers/rss.py
from __future__ import annotations
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Path, Body, Header
from pydantic import BaseModel, Field
from bson import ObjectId

from ..models import TextIn, ExtractOptions, ExtractOut
from ..services.extract_pipeline import run_extract_pipeline
from ..services.mongo_simple import MongoService

# 인스턴스 생성
mongo = MongoService()

router = APIRouter(prefix="/v1/rss", tags=["rss"])

# ---------- Pydantic Schemas ----------
class RssEntryOut(BaseModel):
    id: str
    title: Optional[str] = None
    link: Optional[str] = None
    source: Optional[str] = None
    published: Optional[str] = None
    processed: Optional[bool] = False

class RssEntriesPage(BaseModel):
    total: int
    page: int
    size: int
    items: List[RssEntryOut]

class ProcessAllRequest(BaseModel):
    feed_id: Optional[str] = Field(None, description="특정 feed_id 필터")
    source_domain: Optional[str] = Field(None, description="source 도메인 필터")
    processed: Optional[bool] = Field(None, description="처리 여부 필터")
    limit: int = Field(200, ge=1, le=5000, description="최대 처리 개수")
    mode: Literal["extract", "index", "extract_index"] = "extract"

# ---------- Helpers ----------
def _oid(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="invalid entry_id")

def _serialize_entry(doc: Dict[str, Any]) -> RssEntryOut:
    # 필드 이름이 소스별로 다를 수 있으므로 유연하게 매핑
    title = doc.get("title") or doc.get("headline") or ""
    link = doc.get("link") or doc.get("url")
    published = (
        doc.get("published")
        or doc.get("published_at")
        or doc.get("date")
    )
    if isinstance(published, datetime):
        published = published.isoformat()

    return RssEntryOut(
        id=str(doc.get("_id")),
        title=title,
        link=link,
        source=doc.get("source") or doc.get("source_domain"),
        published=published,
        processed=bool(doc.get("processed", False)),
    )

def _entry_to_textin(doc: Dict[str, Any]) -> TextIn:
    # RSS entry -> TextIn 표준화
    title = doc.get("title") or doc.get("headline") or ""
    # 본문 후보 필드: summary/content/description 중 우선순위
    content = (
        doc.get("content")
        or doc.get("summary")
        or doc.get("description")
        or ""
    )
    return TextIn(id=str(doc["_id"]), title=title, content=content)

def _default_extract_options() -> ExtractOptions:
    # all 파이프라인 on
    opts = ExtractOptions()
    if hasattr(opts, "summary"):      opts.summary.enable = True
    if hasattr(opts, "keywords"):     opts.keywords.enable = True
    if hasattr(opts, "tags"):         opts.tags.enable = True
    if hasattr(opts, "categories"):   opts.categories.enable = True
    return opts

# ---------- Endpoints ----------

@router.get("/entries", response_model=RssEntriesPage)
def list_entries(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    feed_id: Optional[str] = Query(None),
    source_domain: Optional[str] = Query(None),
    processed: Optional[bool] = Query(None),
    q: Optional[str] = Query(None, description="간단 검색(title, link에 contains)"),
    db = Depends(mongo.get_database),
):
    col = db["rss_entries"]
    query: Dict[str, Any] = {}

    if feed_id:
        # 도입한 feed_id 필드를 우선, 없다면 feed/link 등으로 fallback
        query["$or"] = [
            {"feed_id": feed_id},
            {"feed": feed_id},
        ]
    if source_domain:
        query["$or"] = query.get("$or", []) + [
            {"source_domain": source_domain},
            {"source": source_domain},
        ]
    if processed is not None:
        query["processed"] = bool(processed)
    if q:
        query["$or"] = query.get("$or", []) + [
            {"title": {"$regex": q, "$options": "i"}},
            {"link": {"$regex": q, "$options": "i"}},
        ]

    total = col.count_documents(query)
    cursor = (
        col.find(query)
          .sort([("_id", -1)])
          .skip((page - 1) * size)
          .limit(size)
    )
    items = [_serialize_entry(d) for d in cursor]
    return RssEntriesPage(total=total, page=page, size=size, items=items)


@router.get("/entries/{entry_id}", response_model=RssEntryOut)
def get_entry(entry_id: str = Path(...), db = Depends(mongo.get_database)):
    col = db["rss_entries"]
    doc = col.find_one({"_id": _oid(entry_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="entry not found")
    return _serialize_entry(doc)


@router.post("/entries/{entry_id}/process", response_model=ExtractOut)
def process_entry(
    entry_id: str = Path(...),
    idempotency_key: Optional[str] = Header(default=None),
    db = Depends(mongo.get_database),
):
    """
    단일 RSS 엔트리를 추출 파이프라인으로 처리하고, 결과를 articles에 upsert + processed=true 표시
    """
    rss_col = db["rss_entries"]
    art_col = db["articles"]

    doc = rss_col.find_one({"_id": _oid(entry_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="entry not found")

    # 파이프라인 실행
    text_in = _entry_to_textin(doc)
    out = run_extract_pipeline([text_in], _default_extract_options(), idempotency_key)

    # 결과 저장(간단 매핑)
    result_item = out.results[0] if out.results else None
    if result_item:
        art_doc = {
            "_id": _oid(entry_id),  # 동일 id 유지
            "title": text_in.title,
            "content": text_in.content,
            "source": doc.get("source") or doc.get("source_domain"),
            "link": doc.get("link") or doc.get("url"),
            "published": doc.get("published") or doc.get("published_at"),
            "keywords": [k.text for k in (result_item.keywords or [])],
            "tags": result_item.tags or [],
            "categories": [c.name for c in (result_item.categories or [])],
            "updated_at": datetime.utcnow(),
        }
        art_col.replace_one({"_id": art_doc["_id"]}, art_doc, upsert=True)
        rss_col.update_one({"_id": art_doc["_id"]}, {"$set": {"processed": True}})

    return out


@router.post("/feeds/{feed_id}/process", response_model=Dict[str, Any])
def process_feed(
    feed_id: str = Path(...),
    limit: int = Query(200, ge=1, le=5000),
    idempotency_key: Optional[str] = Header(default=None),
    db = Depends(mongo.get_database),
):
    """
    feed_id에 속한 엔트리들을 순차 처리(동기). 대량이면 배치 잡으로 전환 권장.
    """
    rss_col = db["rss_entries"]
    art_col = db["articles"]

    query = {"$or": [{"feed_id": feed_id}, {"feed": feed_id}]}
    cursor = rss_col.find(query).sort([("_id", 1)]).limit(limit)

    count = 0
    for doc in cursor:
        text_in = _entry_to_textin(doc)
        out = run_extract_pipeline([text_in], _default_extract_options(), idempotency_key)
        result_item = out.results[0] if out.results else None
        if result_item:
            art_doc = {
                "_id": doc["_id"],
                "title": text_in.title,
                "content": text_in.content,
                "source": doc.get("source") or doc.get("source_domain"),
                "link": doc.get("link") or doc.get("url"),
                "published": doc.get("published") or doc.get("published_at"),
                "keywords": [k.text for k in (result_item.keywords or [])],
                "tags": result_item.tags or [],
                "categories": [c.name for c in (result_item.categories or [])],
                "updated_at": datetime.utcnow(),
            }
            art_col.replace_one({"_id": art_doc["_id"]}, art_doc, upsert=True)
            rss_col.update_one({"_id": art_doc["_id"]}, {"$set": {"processed": True}})
            count += 1

    return {"processed": count, "limit": limit, "feed_id": feed_id}


@router.post("/entries/process-all", response_model=Dict[str, Any])
def process_all_entries(
    req: ProcessAllRequest = Body(...),
    idempotency_key: Optional[str] = Header(default=None),
    db = Depends(mongo.get_database),
):
    """
    조건 기반 배치 처리(동기). 트래픽이 많다면 잡/큐로 넘기는 걸 권장.
    """
    rss_col = db["rss_entries"]
    art_col = db["articles"]

    query: Dict[str, Any] = {}
    if req.feed_id:
        query["$or"] = [{"feed_id": req.feed_id}, {"feed": req.feed_id}]
    if req.source_domain:
        query["$or"] = query.get("$or", []) + [
            {"source_domain": req.source_domain},
            {"source": req.source_domain},
        ]
    if req.processed is not None:
        query["processed"] = bool(req.processed)

    processed = 0
    cursor = rss_col.find(query).sort([("_id", 1)]).limit(req.limit)

    if req.mode in ("extract", "extract_index"):
        for doc in cursor:
            text_in = _entry_to_textin(doc)
            out = run_extract_pipeline([text_in], _default_extract_options(), idempotency_key)
            result_item = out.results[0] if out.results else None
            if result_item:
                art_doc = {
                    "_id": doc["_id"],
                    "title": text_in.title,
                    "content": text_in.content,
                    "source": doc.get("source") or doc.get("source_domain"),
                    "link": doc.get("link") or doc.get("url"),
                    "published": doc.get("published") or doc.get("published_at"),
                    "keywords": [k.text for k in (result_item.keywords or [])],
                    "tags": result_item.tags or [],
                    "categories": [c.name for c in (result_item.categories or [])],
                    "updated_at": datetime.utcnow(),
                }
                art_col.replace_one({"_id": art_doc["_id"]}, art_doc, upsert=True)
                rss_col.update_one({"_id": art_doc["_id"]}, {"$set": {"processed": True}})
                processed += 1

    return {"processed": processed, "mode": req.mode, "limit": req.limit}
