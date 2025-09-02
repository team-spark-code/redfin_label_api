from __future__ import annotations
from typing import List, Optional
import hashlib
from cachetools import TTLCache

from ..models import (
    TextIn, ExtractOptions, ExtractOut,
    ExtractOutItem, KeywordItem, CategoryItem,
)
from .extract_keywords import extract_keywords_from_text
from .extract_tags import get_tags_with_ollama, controlled_vocab
from .extract_category import classifier
from .tag_cleaner import clean_tags_entry

# 간단한 메모리 캐시 (15분)
_EXTRACT_CACHE = TTLCache(maxsize=10_000, ttl=900)

def _strip_ollama_prefix(name: Optional[str]) -> Optional[str]:
    if not name:
        return name
    return name.split("ollama:", 1)[1] if name.startswith("ollama:") else name

def _to_keyword_items(kws: List[str]) -> List[KeywordItem]:
    return [KeywordItem(text=k, score=1.0) for k in kws if k]

def _to_category_items(cat: Optional[str], conf: Optional[float]) -> List[CategoryItem]:
    if not cat:
        return []
    return [CategoryItem(name=cat, score=float(conf or 0.0))]

def _hash_request(texts: List[TextIn], options: ExtractOptions) -> str:
    h = hashlib.sha256()
    for t in texts:
        title = getattr(t, "title", None) or ""
        # description -> content 승격을 허용
        content = getattr(t, "content", None) or getattr(t, "description", None) or ""
        h.update((t.id + title + content).encode("utf-8"))
    h.update(str(options.model_dump()).encode("utf-8"))
    return h.hexdigest()


def run_extract_pipeline(
    texts: List[TextIn],
    options: ExtractOptions,
    idempotency_key: Optional[str] = None,
) -> ExtractOut:
    """
    라우터(app/routers/extract.py)에서 직접 호출하는 메인 파이프라인.
    
    옵션별 분리 처리, 내부에서 idempotency 캐시 처리 가능
    
    TODO:
    - 요약(summary)은 현재 내부 로직이 없으므로 메타에만 표기(필요 시 후속 구현).
    - keywords/tags/categories는 옵션에 따라 개별 처리.
    - idempotency_key가 오면 캐시 키로 사용.
    """
    cache_key = idempotency_key or _hash_request(texts, options)
    if cache_key in _EXTRACT_CACHE:
        return _EXTRACT_CACHE[cache_key]

    model_for_tags = _strip_ollama_prefix(
        getattr(getattr(options, "tags", None), "model", None)
    )

    results: List[ExtractOutItem] = []

    for doc in texts:
        doc_id = doc.id
        title = (getattr(doc, "title", None) or "").strip()
        content = (
            getattr(doc, "content", None)
            or getattr(doc, "description", None)
            or ""
        ).strip()

        # 1) Keywords
        keywords: List[str] = []
        if getattr(options, "keywords", None) and options.keywords.enable:
            top_k = int(getattr(options.keywords, "top_k", 10) or 10)
            keywords = extract_keywords_from_text(title, content, top_k=top_k)
        kw_items = _to_keyword_items(keywords)

        # 2) Tags
        tags: List[str] = []
        if getattr(options, "tags", None) and options.tags.enable:
            tags = get_tags_with_ollama(
                title=title,
                content=content,
                yake_keywords=keywords,
                vocab=controlled_vocab,
                model_name=model_for_tags,
                server_name="remote",  # 원격 서버 사용 (환경설정으로 전환 가능)
            )
            tags = clean_tags_entry(tags)

        # 3) Category (단일)
        cat_items: List[CategoryItem] = []
        if getattr(options, "categories", None) and options.categories.enable:
            res = classifier.classify_article(
                title=title,
                description=content,
                keywords=", ".join(keywords),
            )
            cat_items = _to_category_items(res.get("category"), res.get("confidence"))

        results.append(
            ExtractOutItem(
                id=doc_id,
                keywords=kw_items,
                tags=tags,
                tags_struct=None,
                categories=cat_items,
            )
        )

    out = ExtractOut(
        results=results,
        meta={
            "algo": getattr(getattr(options, "keywords", None), "algo", None),
            "model": model_for_tags,
            "scheme": getattr(getattr(options, "categories", None), "scheme", None),
        },
    )
    _EXTRACT_CACHE[cache_key] = out
    return out