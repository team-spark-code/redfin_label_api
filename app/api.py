import time
import uuid
import hashlib
import logging 
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Header, HTTPException, Query, File, UploadFile
from fastapi.responses import JSONResponse

from .models import (
    ExtractIn, ExtractOut, ExtractOutItem,
    KeywordItem, CategoryItem,
    JobIn, JobStatus,
    OptKeywords, OptTags, OptCategories, ExtractOptions,
)
# 서비스
from .services.extract_keywords import extract_keywords_text
from .services.extract_tags import get_tags_with_ollama, controlled_vocab
from .services.extract_category import classifier
from .services.tag_cleaner import clean_tags_entry
from .services.article_recom import ArticleService
from .services import mongo_simple

router = APIRouter()


# ---- Configuration for Elasticsearch ----
ES_HOST = "http://192.168.0.123:9200"
ES_AUTH = ("elastic", "elastic")
INDEX_NAME = "article_recommender"

# Initialize ArticleService
article_service = ArticleService(ES_HOST, ES_AUTH, INDEX_NAME)


# ---- in-memory stores (demo) ----
_JOBS: Dict[str, Dict[str, Any]] = {}
_RESULTS: Dict[str, List[Dict[str, Any]]] = {}
_EXTRACT_CACHE: Dict[str, Any] = {}

# ---- utils ----
def _hash_extract_request(body: ExtractIn) -> str:
    h = hashlib.sha256()
    for t in body.texts:
        h.update((t.id + (t.title or "") + t.content).encode("utf-8"))
    h.update(str(body.options.model_dump()).encode("utf-8"))
    return h.hexdigest()

def _strip_ollama_prefix(name: str) -> str:
    # "ollama:gemma3:4b" → "gemma3:4b"
    if name.startswith("ollama:"):
        return name.split("ollama:", 1)[1]
    return name

def _to_keyword_items(kws: List[str]) -> List[KeywordItem]:
    return [KeywordItem(text=k, score=1.0) for k in kws if k]

def _to_category_items(cat: str, conf: float) -> List[CategoryItem]:
    if not cat:
        return []
    return [CategoryItem(name=cat, score=float(conf or 0.0))]

# ---- health & catalog ----
@router.get("/health")
def health():
    return {"status": "ok", "ts": int(time.time())}

@router.get("/catalog/categories")
def catalog_categories():
    # ArticleClassifier가 가진 카테고리 반환
    return {"scheme": "redfin-minds-2025", "labels": classifier.get_available_categories()}

@router.get("/catalog/tags")
def catalog_tags():
    # controlled_vocab 카테고리별 후보를 납품
    return {"tags_catalog": controlled_vocab}

# ---- /extract ----
@router.post("/extract", response_model=ExtractOut)
def extract(body: ExtractIn, idempotency_key: Optional[str] = Header(default=None)):
    cache_key = idempotency_key or _hash_extract_request(body)
    if cache_key in _EXTRACT_CACHE:
        return _EXTRACT_CACHE[cache_key]

    opts = body.options
    model_for_tags = _strip_ollama_prefix(opts.tags.model)

    results: List[ExtractOutItem] = []
    for doc in body.texts:
        title = doc.title or ""
        content = doc.content or ""

        # 1) 키워드
        keywords = extract_keywords_text(title, content, top_k=opts.keywords.top_k) if opts.keywords.enable else []
        kw_items = _to_keyword_items(keywords)

        # 2) 태그('cat/Keyword')
        tags: List[str] = []
        if opts.tags.enable:
            tags = get_tags_with_ollama(
                title=title,
                content=content,
                yake_keywords=keywords,
                vocab=controlled_vocab,
                model_name=model_for_tags,
                server_name="remote"  # 원격 서버 사용
            )
            # 태깅 전처리 과정 추가 
            tags = clean_tags_entry(tags)
            # 모델 검증층에서 'cat/Keyword' 패턴 정규화/검증 수행됨

        # 3) 카테고리(단일)
        cat_items: List[CategoryItem] = []
        if opts.categories.enable:
            res = classifier.classify_article(title=title, description=content, keywords=", ".join(keywords))
            cat_items = _to_category_items(res.get("category"), res.get("confidence"))

        results.append(
            ExtractOutItem(
                id=doc.id,
                keywords=kw_items,
                tags=tags,
                tags_struct=None,
                categories=cat_items,
            )
        )

    out = ExtractOut(results=results, meta={
        "algo": opts.keywords.algo,
        "model": model_for_tags,
        "scheme": opts.categories.scheme,
    })
    _EXTRACT_CACHE[cache_key] = out
    return out

# ---- /jobs ----
@router.post("/jobs")
def create_job(body: JobIn):
    job_id = str(uuid.uuid4())
    _JOBS[job_id] = {
        "status": "queued",
        "progress": 0,
        "created_at": int(time.time()),
        "mode": body.mode,
        "error": None,
        "total": 0,
        "done": 0,
    }

    try:
        if body.mode == "inline":
            payload = body.payload or {}
            texts = payload.get("texts", [])
            _JOBS[job_id]["total"] = len(texts)

            # /extract 경로 재사용
            out = extract(ExtractIn(texts=texts, options=body.options))  # type: ignore
            _RESULTS[job_id] = [r.model_dump() for r in out.results]
            _JOBS[job_id].update(status="succeeded", progress=100, done=len(_RESULTS[job_id]))

        elif body.mode == "connector":
            conn = body.connector
            if not conn or conn.type != "mongo":
                raise HTTPException(400, "unsupported or missing connector")

            docs = list(mongo_simple.stream_docs(
                uri=conn.uri, db=conn.db, collection=conn.collection,
                flt=conn.filter, proj=conn.projection, batch_size=conn.batch_size
            ))
            _JOBS[job_id]["total"] = len(docs)

            # Mongo 문서를 TextIn 호환 dict로 변환
            texts = []
            for d in docs:
                texts.append({
                    "id": str(d.get("_id")),
                    "title": d.get("title") or d.get("headline") or "",
                    # TextIn이 description→content를 자동 승격
                    "description": d.get("description") or d.get("abstract") or d.get("content") or d.get("article") or "",
                    "url": d.get("url") or "",
                    "lang": d.get("lang") or "en",
                    # 사전 키워드/태그가 있으면 함께 전달(선택)
                    "keywords": d.get("keywords"),
                    "tags": d.get("tags"),
                })

            out = extract(ExtractIn(texts=texts, options=body.options))  # type: ignore
            _RESULTS[job_id] = [r.model_dump() for r in out.results]
            _JOBS[job_id].update(status="succeeded", progress=100, done=len(_RESULTS[job_id]))

            # conn.update_mode(update|upsert) 저장은 별도 writer 서비스 권장
        else:
            raise HTTPException(400, "invalid mode")

    except Exception as e:
        _JOBS[job_id].update(status="failed", error=str(e))

    return {"job_id": job_id, "status": _JOBS[job_id]["status"]}

@router.get("/jobs/{job_id}", response_model=JobStatus)
def job_status(job_id: str):
    j = _JOBS.get(job_id)
    if not j:
        raise HTTPException(404, "job not found")
    return {
        "job_id": job_id,
        "status": j["status"],
        "progress": j["progress"],
        "total": j["total"],
        "done": j["done"],
        "error": j["error"],
        "created_at": j["created_at"],
    }

@router.get("/jobs/{job_id}/results")
def job_results(job_id: str, page: int = Query(1, ge=1), size: int = Query(100, ge=1, le=1000)):
    items = _RESULTS.get(job_id)
    if items is None:
        raise HTTPException(404, "no results for job")
    start = (page - 1) * size
    end = start + size
    return {"job_id": job_id, "page": page, "size": size, "total": len(items), "items": items[start:end]}

@router.post("/jobs/{job_id}/cancel")
def job_cancel(job_id: str):
    j = _JOBS.get(job_id)
    if not j:
        raise HTTPException(404, "job not found")
    j["status"] = "canceled"
    return {"job_id": job_id, "status": "canceled"}

# ---- connector sanity ----
@router.get("/connectors/mongo/test")
def mongo_test(uri: str, db: str, collection: str):
    return mongo_simple.ping(uri, db, collection)

# ---- RSS 데이터 관련 엔드포인트 ----
@router.get("/rss/entries")
def get_rss_entries(
    limit: int = Query(default=10, ge=1, le=1000),
    skip: int = Query(default=0, ge=0),
    title_contains: Optional[str] = Query(default=None)
):
    """RSS 엔트리 목록 조회"""
    filter_dict = {}
    if title_contains:
        filter_dict["title"] = {"$regex": title_contains, "$options": "i"}
    
    entries = mongo_simple.get_rss_entries(limit=limit, skip=skip, filter_dict=filter_dict)
    total_count = mongo_simple.count_rss_entries(filter_dict=filter_dict)
    
    return {
        "entries": entries,
        "pagination": {
            "total": total_count,
            "limit": limit,
            "skip": skip,
            "has_more": skip + limit < total_count
        }
    }

@router.get("/rss/entries/count")
def get_rss_entries_count():
    """RSS 엔트리 총 개수 조회"""
    count = mongo_simple.count_rss_entries()
    return {"total_count": count}

@router.get("/rss/entries/{entry_id}")
def get_rss_entry(entry_id: str):
    """특정 RSS 엔트리 조회"""
    from bson import ObjectId
    try:
        # ObjectId로 변환 시도
        object_id = ObjectId(entry_id)
        filter_dict = {"_id": object_id}
    except:
        # ObjectId가 아니면 문자열로 검색
        filter_dict = {"_id": entry_id}
    
    entries = mongo_simple.get_rss_entries(limit=1, filter_dict=filter_dict)
    if not entries:
        raise HTTPException(404, "RSS entry not found")
    
    return {"entry": entries[0]}

@router.get("/rss/test-connection")
def test_rss_connection():
    """RSS MongoDB 연결 테스트"""
    from .core.config import settings
    return mongo_simple.ping(
        uri=settings.MONGODB_URI,
        db=settings.MONGODB_DB,
        collection=settings.MONGODB_COLLECTION
    )

# ---- RSS 전체 배치 처리 ----
@router.post("/rss/process-all")
def process_all_rss_entries(
    batch_size: int = Query(default=50, ge=1, le=500),
    skip_existing: bool = Query(default=True),
    test_mode: bool = Query(default=False)
):
    """RSS 컬렉션의 모든 엔트리에 대해 키워드, 태그, 카테고리 처리"""
    from .core.config import settings
    
    # 기존 배치 작업과 동일한 방식으로 JobIn 생성
    job_payload = {
        "mode": "connector",
        "connector": {
            "type": "mongo",
            "uri": settings.MONGODB_URI,
            "db": settings.MONGODB_DB,
            "collection": settings.MONGODB_COLLECTION,
            "filter": {"processed": {"$ne": True}} if skip_existing else {},
            "batch_size": batch_size,
            "update_mode": "upsert" if not test_mode else "none"
        },
        "options": {
            "keywords": {"enable": True, "algo": "yake", "top_k": 10},
            "tags": {"enable": True, "model": "ollama:gemma3:4b", "top_k": 8},
            "categories": {"enable": True, "scheme": "redfin-minds-2025", "multi_label": True}
        }
    }
    
    # JobIn으로 변환
    job_in = JobIn(**job_payload)
    
    # 기존 create_job 함수 재사용
    return create_job(job_in)

@router.post("/rss/process-sample")
def process_sample_rss_entries(
    limit: int = Query(default=10, ge=1, le=100),
    skip: int = Query(default=0, ge=0)
):
    """RSS 엔트리 샘플에 대해 키워드, 태그, 카테고리 처리 (테스트용)"""
    # RSS 엔트리 가져오기
    entries = mongo_simple.get_rss_entries(limit=limit, skip=skip)
    
    if not entries:
        return {"message": "처리할 엔트리가 없습니다.", "count": 0}
    
    # TextIn 형식으로 변환
    texts = []
    for entry in entries:
        text_data = {
            "id": entry.get("_id", "unknown"),
            "title": entry.get("title", ""),
            "description": entry.get("description", ""),  # TextIn이 자동으로 content로 변환
            "url": entry.get("url", ""),
            "lang": entry.get("lang", "en")
        }
        texts.append(text_data)
    
    # ExtractIn으로 처리
    extract_request = ExtractIn(
        texts=texts,
        options=ExtractOptions(
            keywords=OptKeywords(enable=True, algo="yake", top_k=10),
            tags=OptTags(enable=True, model="ollama:gemma3:4b", top_k=8),
            categories=OptCategories(enable=True, scheme="redfin-minds-2025", multi_label=True)
        )
    )
    
    # 처리 실행
    result = extract(extract_request)
    
    return {
        "message": f"{len(entries)}개 엔트리 처리 완료",
        "count": len(entries),
        "results": result.results,
        "meta": result.meta
    }

@router.get("/rss/processing-status")
def get_processing_status():
    """RSS 컬렉션의 처리 상태 조회"""
    from .core.config import settings
    
    # 전체 문서 수
    total_count = mongo_simple.count_rss_entries()
    
    # 처리된 문서 수 (processed: true 필드가 있는 것들)
    processed_count = mongo_simple.count_rss_entries({"processed": True})
    
    # 진행률 계산
    progress_percentage = (processed_count / total_count * 100) if total_count > 0 else 0
    
    return {
        "total_entries": total_count,
        "processed_entries": processed_count,
        "remaining_entries": total_count - processed_count,
        "progress_percentage": round(progress_percentage, 2),
        "collection": settings.MONGODB_COLLECTION,
        "database": settings.MONGODB_DB
    }



# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ---- 추천 엔드포인트 ----

@router.post("/recommendations/index", response_model=dict)
async def index_articles(file: UploadFile = File(...)):
    """기사들을 Elasticsearch에 인덱싱하여 추천 시스템에 활용하는 엔드포인트"""
    
    # 파일 확장자 검증 - .jsonl 파일만 허용
    if not file.filename.endswith('.jsonl'):
        raise HTTPException(status_code=400, detail="파일은 .jsonl 형식이어야 합니다")
    
    try:
        # 업로드된 파일을 임시로 저장
        content = await file.read()
        temp_file_path = f"/tmp/{file.filename}"
        with open(temp_file_path, 'wb') as f:
            f.write(content)
        
        # 기사 데이터 로드 및 인덱싱
        articles = article_service.load_jsonl_data(temp_file_path)
        if not articles:
            raise HTTPException(status_code=400, detail="파일에서 유효한 기사를 찾을 수 없습니다")
        
        # 기사들을 Elasticsearch에 인덱싱
        total_indexed = article_service.index_articles(articles)
        return {"message": f"총 {total_indexed}개의 기사가 성공적으로 인덱싱되었습니다"}
        
    except Exception as e:
        logger.error(f"기사 인덱싱 오류: {e}")
        raise HTTPException(status_code=500, detail=f"기사 인덱싱 실패: {str(e)}")


@router.get("/recommendations/search", response_model=List[Dict])
async def search_recommendations(
    query: str, 
    top_k: int = Query(default=5, ge=1, le=20),
    group: Optional[str] = Query(default=None)
):
    """쿼리를 기반으로 기사 추천을 검색하는 엔드포인트"""
    
    try:
        # 그룹 필터 설정 (선택사항)
        filters = {"match": {"group": group}} if group else None
        
        # 추천 검색 실행
        recommendations = article_service.search_recommendations(query, top_k, filters)
        return recommendations
        
    except Exception as e:
        logger.error(f"추천 검색 오류: {e}")
        raise HTTPException(status_code=500, detail=f"추천 검색 실패: {str(e)}")


@router.post("/rss/recommendations/process-all")
def process_all_rss_for_recommendations(
    batch_size: int = Query(default=50, ge=1, le=500),
    skip_existing: bool = Query(default=True)
):
    """모든 RSS 항목을 추천 인덱싱을 위해 처리하는 엔드포인트"""
    
    from .core.config import settings
    
    # 고유한 작업 ID 생성
    job_id = str(uuid.uuid4())
    
    # 작업 상태 초기화
    _JOBS[job_id] = {
        "status": "대기중",          # 작업 상태
        "progress": 0,              # 진행률 (%)
        "created_at": int(time.time()),  # 생성 시간
        "mode": "connector",        # 작업 모드
        "error": None,             # 오류 메시지
        "total": 0,                # 총 처리할 문서 수
        "done": 0,                 # 완료된 문서 수
    }
    
    try:
        # MongoDB에서 RSS 문서들을 스트리밍으로 가져오기
        # skip_existing이 True면 이미 처리된 문서는 제외
        docs = list(mongo_simple.stream_docs(
            uri=settings.MONGODB_URI,
            db=settings.MONGODB_DB,
            collection=settings.MONGODB_COLLECTION,
            flt={"processed": {"$ne": True}} if skip_existing else {},  # 필터 조건
            batch_size=batch_size
        ))
        
        # 총 문서 수 업데이트
        _JOBS[job_id]["total"] = len(docs)
        
        # MongoDB 문서를 추천 시스템용 기사 형태로 변환
        articles = []
        for d in docs:
            articles.append({
                "guid": str(d.get("_id")),  # 고유 식별자
                "title": d.get("title") or d.get("headline") or "",  # 제목
                "description": (d.get("description") or d.get("abstract") or 
                              d.get("content") or d.get("article") or ""),  # 내용
                "keywords": d.get("keywords", [])  # 키워드 목록
            })
        
        # 기사들을 Elasticsearch에 인덱싱
        total_indexed = article_service.index_articles(articles)
        
        # 작업 완료 상태 업데이트
        _JOBS[job_id].update(status="성공", progress=100, done=total_indexed)
        
        return {
            "job_id": job_id, 
            "status": "성공", 
            "total_indexed": total_indexed
        }
        
    except Exception as e:
        # 오류 발생 시 작업 상태 업데이트
        _JOBS[job_id].update(status="실패", error=str(e))
        raise HTTPException(
            status_code=500, 
            detail=f"RSS 항목 추천 처리 실패: {str(e)}"
        )