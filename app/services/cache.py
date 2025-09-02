import hashlib
from cachetools import TTLCache
from .extract_pipeline import run_extract_pipeline

_EXTRACT_CACHE = TTLCache(maxsize=10_000, ttl=900)

# TODO: Implement this
def _hash_request(texts, options) -> str:
    h = hashlib.sha256()
    for t in texts:
        title = getattr(t, "title", None) or ""
        content = getattr(t, "content", None) or getattr(t, "description", None) or ""
        h.update((t.id + title + content).encode("utf-8"))
    h.update(str(options.model_dump()).encode("utf-8"))
    return h.hexdigest()

def run_with_cache(texts, options, idempotency_key: str | None):
    key = idempotency_key or _hash_request(texts, options)
    if key in _EXTRACT_CACHE:
        return _EXTRACT_CACHE[key]
    out = run_extract_pipeline(texts, options)
    _EXTRACT_CACHE[key] = out
    return out
