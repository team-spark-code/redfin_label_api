import pandas as pd
import ast
import html
from typing import List, Union, Optional

# -----------------------------
# Tag Normalization & Cleaning
# -----------------------------
TAG_FIXES = {
    "biz/Regulation": "policy/Regulation",
    "event/Funding": "biz/Funding", 
    "domain/Multimodal": "topic/Multimodal",
    "event/NA": "event/Unknown",
    "domain/SocialNetwork": "domain/SocialMedia",
    "domain/SpaceExploration": "domain/Space",
    "domain/Multimedia": "domain/Media",
    "domain/ImageEditing": "domain/Media",
    "domain/Photoshop": "domain/Media",
    "domain/FutureWorkplace": "domain/Workplace",
    "domain/ConsumerElectronics": "domain/Technology",
}

VALID_PREFIXES = (
    "org/", "model/", "domain/", "topic/",
    "event/", "geo/", "biz/", "policy/"
)


def normalize_tag(tag: str) -> Optional[str]:
    """
    Normalize and validate a single tag string.
    Returns None if the tag is invalid.
    """
    if not isinstance(tag, str):
        return None

    # 1. Decode HTML escapes (&amp; → &)
    tag = html.unescape(tag.strip())

    # 2. Skip tags with invalid chars or patterns
    if '\\' in tag or any(ch in tag for ch in ['*', ':', '**']):
        return None

    # 3. Remove anything after newline
    tag = tag.split('\n')[0]

    # 4. Handle malformed tags with multiple slashes (keep only first two parts)
    if tag.count('/') > 1:
        parts = tag.split('/')
        if len(parts) >= 2:
            tag = f"{parts[0]}/{parts[1]}"
        else:
            return None

    # 5. Remove spaces inside tags
    tag = tag.replace(" ", "")

    # 6. Fix known misclassifications
    tag = TAG_FIXES.get(tag, tag)

    # 7. Validate prefix & value
    if not tag.startswith(VALID_PREFIXES):
        return None

    prefix, _, value = tag.partition('/')
    if not value.strip():  # empty value
        return None

    return tag


# -----------------------------
# Tag Processing
# -----------------------------
def parse_tag_entry(tag_entry: Union[str, List[str]]) -> List[str]:
    """
    Convert a tag entry (string, list, etc.) into a list of strings.
    - If string looks like a Python list, parse it safely.
    - Otherwise, split by commas.
    """
    if isinstance(tag_entry, str):
        try:
            parsed = ast.literal_eval(tag_entry)
            if isinstance(parsed, list):
                return parsed
        except (ValueError, SyntaxError):
            return [t.strip() for t in tag_entry.split(',') if t.strip()]
        return [tag_entry.strip()]
    elif isinstance(tag_entry, list):
        return tag_entry
    else:
        return []


def clean_tags_entry(tag_entry: Union[str, List[str]]) -> List[str]:
    """
    Clean and deduplicate a single tag entry (string or list).
    """
    tags = parse_tag_entry(tag_entry)
    seen, cleaned = set(), []

    for raw_tag in tags:
        normalized = normalize_tag(raw_tag)
        if normalized and normalized not in seen:
            seen.add(normalized)
            cleaned.append(normalized)

    return cleaned


def clean_tags_series(tags_series: pd.Series) -> pd.Series:
    """
    Apply cleaning to an entire pandas Series of tag entries.
    """
    return tags_series.apply(clean_tags_entry)
