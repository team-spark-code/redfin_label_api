# /extract + /jobs + /catalog/* 설계에 맞춘 Pydantic 모델
from __future__ import annotations
from typing import Any, Dict, List, Literal, Optional, Annotated, Tuple
from pydantic import BaseModel, Field, ConfigDict, field_validator
from pydantic.types import StringConstraints

# Common Types
TagCategory = Literal["org", "model", "domain", "topic", "event", "geo", "biz", "policy"]
TagString = Annotated[str, StringConstraints(pattern=r"^[a-z]+/[A-Za-z0-9][A-Za-z0-9 .+\-_/]*$")]

# Input Source: RSS Feed Entries's title, description
# JSON {title, description} or API {title, content}
class TextIn(BaseModel):
    """
    단일 문서 입력. JSONL의 'description'을 'content'로 자동 승격
    """
    model_config = ConfigDict(extra="allow") # 필요 시 부가 필드 통과
    
    id: str
    title: Optional[str] = None
    content: str
    url: Optional[str] = None
    lang: Optional[str] = None

    @classmethod
    def _pick_first(cls, data: Dict[str, Any], keys: List[str], default: str = "") -> str:
        for key in keys:
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return default

    @classmethod
    def _coerce_content(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        # content가 없으면 description/headline/body 순서로 채움
        if "content" not in data or not (isinstance(data.get("content"), str) and data["content"].strip()):
            data["content"] = cls._pick_first(data, ["description", "headline", "body"], default="")
        return data
    
    @classmethod
    def model_validate(cls, obj: Any, *, strict: bool | None = None, from_attributes: bool | None = None, context: Dict[str, Any] | None = None) -> "TextIn":
        # Pydantic v2에서 사전 전처리용 오버라이드
        if isinstance(obj, dict):
            obj = dict(obj)  # shallow copy
            obj = cls._coerce_content(obj)
        return super().model_validate(obj, strict=strict, from_attributes=from_attributes, context=context)


# ------------------------------------------------------------
# Options (Algorithm/Model Selection)
# ------------------------------------------------------------
class OptKeywords(BaseModel):
    enable: bool = True
    algo: Literal["yake","textrank","none"] = "yake"
    top_k: int = 10

class OptTags(BaseModel):
    enable: bool = True
    model: str = "ollama:gemma3:4b"
    top_k: int = 8

class OptCategories(BaseModel):
    enable: bool = True
    scheme: str = "redfin-minds-2025"
    multi_label: bool = True
    threshold: float = 0.30

class ExtractOptions(BaseModel):
    keywords: OptKeywords = OptKeywords()
    tags: OptTags = OptTags()
    categories: OptCategories = OptCategories()


# ------------------------------------------------------------
# /extract 요청/응답
# ------------------------------------------------------------
class ExtractIn(BaseModel):
    texts: List[TextIn]
    options: ExtractOptions = ExtractOptions()

class KeywordItem(BaseModel):
    text: str
    score: float = Field(default=1.0, ge=0.0, le=1.0)

class TagItem(BaseModel):
    category: TagCategory
    keyword: str
    score: float = Field(default=0.8, ge=0.0, le=1.0)

    @field_validator("keyword")
    @classmethod
    def _normalize_keyword(cls, v: str) -> str:
        # category/Keyword에서 Keyword 표준화(첫 글자 대문자) - 서비스 규칙에 맞게 조정 가능
        return v[:1].upper() + v[1:] if v else v

    def to_tagstr(self) -> str:
        return f"{self.category}/{self.keyword}"

    @classmethod
    def from_tagstr(cls, tag: str, score: float = 0.8) -> "TagItem":
        cat, kw = _split_tag(tag)
        return cls(category=cat, keyword=kw, score=score)

def _split_tag(tag: str) -> Tuple[TagCategory, str]:
    if "/" not in tag:
        raise ValueError("tag must be 'category/Keyword' format")
    cat, kw = tag.split("/", 1)
    cat_l = cat.strip().lower()
    if cat_l not in {"org", "model", "domain", "topic", "event", "geo", "biz", "policy"}:
        raise ValueError(f"invalid tag category '{cat}'")
    kw = kw.strip()
    return cat_l, kw  # type: ignore[return-value]

class CategoryItem(BaseModel):
    name: str
    score: float = Field(default=0.8, ge=0.0, le=1.0)

class LabelScore(BaseModel):
    name: str
    score: float

class ExtractOutItem(BaseModel):
    id: str
    keywords: List[KeywordItem] = []
    tags: List[TagString] = []
    tags_struct: Optional[List[TagItem]] = None
    categories: List[CategoryItem] = []

    @field_validator("tags", mode="before")
    @classmethod
    def _ensure_list(cls, v: Any) -> Any:
        # None → [], 단일 문자열 → [str]
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return v

    @field_validator("tags")
    @classmethod
    def _normalize_tags(cls, values: List[str]) -> List[str]:
        # "Cat/keyword" → "cat/Keyword"로 정규화
        normed: List[str] = []
        for t in values:
            cat, kw = _split_tag(t)
            kw = kw[:1].upper() + kw[1:] if kw else kw
            normed.append(f"{cat}/{kw}")
        return normed

class ExtractOut(BaseModel):
    results: List[ExtractOutItem]
    meta: Dict[str, Any] = {}

# ------------------------------------------------------------
# /jobs 요청 스키마 (배치)
#  - mode=="inline"  : payload.texts 로 직접 문서 전달
#  - mode=="connector": Mongo 등 외부 소스 지정
# ------------------------------------------------------------
class MongoConnector(BaseModel):
    type: Literal["mongo"] = "mongo"
    uri: str
    db: str
    collection: str
    filter: Dict[str, Any] = Field(default_factory=dict)
    projection: Dict[str, Any] = Field(default_factory=dict)
    batch_size: int = Field(default=100, ge=1, le=10_000)
    update_mode: Literal["none", "update", "upsert"] = "none"

class JobIn(BaseModel):
    mode: Literal["inline", "connector"]
    payload: Optional[Dict[str, Any]] = None
    connector: Optional[MongoConnector] = None
    options: ExtractOptions = ExtractOptions()

# ------------------------------------------------------------
# 응답/상태(참고: 라우터 구현부에서 사용)
# ------------------------------------------------------------
class JobStatus(BaseModel):
    job_id: str
    status: Literal["queued", "running", "succeeded", "failed", "canceled"]
    progress: int = Field(ge=0, le=100, default=0)
    total: int = 0
    done: int = 0
    error: Optional[str] = None
    created_at: int

# Export all models for easy import
__all__ = [
    "TextIn", "OptKeywords", "OptTags", "OptCategories", "ExtractOptions",
    "ExtractIn", "KeywordItem", "TagItem", "CategoryItem", "LabelScore",
    "ExtractOutItem", "ExtractOut", "MongoConnector", "JobIn", "JobStatus",
    "TagCategory", "TagString"
]