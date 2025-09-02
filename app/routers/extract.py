from typing import Optional

from fastapi import APIRouter, Header
from ..models import ExtractIn, ExtractOut, ExtractOptions
from ..services.extract_pipeline import run_extract_pipeline

router = APIRouter(prefix="/v1/extract", tags=["extract"])

def _opts_only(**parts) -> ExtractOptions:
    opts = ExtractOptions()
    for k, v in parts.items():
        sect = getattr(opts, k, None)
        if sect is not None and hasattr(sect, "enable"):
            sect.enable = bool(v)
    return opts

# 요약만
@router.post("/summary", response_model=ExtractOut)
def extract_summary(body: ExtractIn, idempotency_key: Optional[str] = Header(default=None)):
    opts = _opts_only(summary=True)
    return run_extract_pipeline(body.texts, opts, idempotency_key)


# 키워드만
@router.post("/keywords", response_model=ExtractOut)
def extract_keywords(body: ExtractIn, idempotency_key: Optional[str] = Header(default=None)):
    opts = _opts_only(keywords=True)
    return run_extract_pipeline(body.texts, opts, idempotency_key)


# 태그만
@router.post("/tags", response_model=ExtractOut)
def extract_tags(body: ExtractIn, idempotency_key: Optional[str] = Header(default=None)):
    opts = _opts_only(tags=True)
    return run_extract_pipeline(body.texts, opts, idempotency_key)


# 카테고리만
@router.post("/category", response_model=ExtractOut)
def extract_category(body: ExtractIn, idempotency_key: Optional[str] = Header(default=None)):
    opts = _opts_only(categories=True)
    return run_extract_pipeline(body.texts, opts, idempotency_key)


# 전체 파이프라인
@router.post("/all", response_model=ExtractOut)
def extract_all(body: ExtractIn, idempotency_key: Optional[str] = Header(default=None)):
    opts = _opts_only(summary=True, keywords=True, tags=True, categories=True)
    return run_extract_pipeline(body.texts, opts, idempotency_key)
