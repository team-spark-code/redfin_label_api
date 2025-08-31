# Create a single-file shell script that performs:
# 1) YAKE keywords
# 2) Ollama tag generation
# 3) Ollama category classification
# and saves outputs to a workdir.
import os, stat, textwrap, json, sys, pathlib

script_path = "/mnt/data/rss_yake_tag_cate.sh"

script = r"""#!/usr/bin/env bash
# rss_yake_tag_cate.sh
# YAKE 키워드 → Ollama 태그 → Ollama 카테고리 (JSONL 파이프라인)
# 사용법:
#   bash rss_yake_tag_cate.sh -i /path/to/all_entries.jsonl -o ./out \
#       -t "gemma3:4b" -c "gemma3:4b" -w 2 -k 5 -b 5
#
# 입력(JSONL) 필드 예시: {"title": "...", "description": "..."}
# 출력:
#   out/all_entries_keywords.jsonl
#   out/all_entries_tags.jsonl
#   out/all_entries_categories.jsonl

set -euo pipefail

IN=""
OUT="./data/output"
TAG_MODEL="gemma3:4b"
CAT_MODEL="gemma3:4b"
MAX_WORKERS=2
MAX_KEYWORDS=5
BATCH_SIZE=5

usage() {
  cat <<USAGE
사용법:
  $(basename "$0") -i INPUT.jsonl [-o OUTDIR] [-t TAG_MODEL] [-c CAT_MODEL] [-w MAX_WORKERS] [-k MAX_KEYWORDS] [-b BATCH_SIZE]

옵션 기본값:
  -o ${OUT}
  -t ${TAG_MODEL}
  -c ${CAT_MODEL}
  -w ${MAX_WORKERS}
  -k ${MAX_KEYWORDS}
  -b ${BATCH_SIZE}
USAGE
}

while getopts ":i:o:t:c:w:k:b:h" opt; do
  case ${opt} in
    i) IN="${OPTARG}" ;;
    o) OUT="${OPTARG}" ;;
    t) TAG_MODEL="${OPTARG}" ;;
    c) CAT_MODEL="${OPTARG}" ;;
    w) MAX_WORKERS="${OPTARG}" ;;
    k) MAX_KEYWORDS="${OPTARG}" ;;
    b) BATCH_SIZE="${OPTARG}" ;;
    h) usage; exit 0 ;;
    \?) echo "알 수 없는 옵션: -$OPTARG" >&2; usage; exit 1 ;;
    :) echo "옵션 -$OPTARG 인자가 필요합니다." >&2; usage; exit 1 ;;
  esac
done

if [[ -z "${IN}" ]]; then
  echo "[ERR] -i INPUT.jsonl 을 지정하세요" >&2
  usage
  exit 1
fi

mkdir -p "${OUT}"

# Python/패키지 확인 & 설치
if ! command -v python3 >/dev/null 2>&1; then
  echo "[ERR] python3 가 필요합니다." >&2; exit 1
fi

PYMODS=(yake ollama tqdm pandas)
for m in "${PYMODS[@]}"; do
  python3 - <<'PY' "$m" >/dev/null 2>&1 || true
import importlib, sys
m = sys.argv[1]
importlib.import_module(m)
PY
  if [[ $? -ne 0 ]]; then
    echo "[INFO] pip로 ${m} 설치 중..."
    python3 -m pip install -q --upgrade pip >/dev/null
    python3 -m pip install -q "$m"
  fi
done

# Ollama 확인
if ! command -v ollama >/dev/null 2>&1; then
  echo "[ERR] ollama CLI가 필요합니다. https://ollama.com/ 설치 후 'ollama serve'를 실행하세요." >&2
  exit 1
fi

# 모델 프리풀(없으면 자동 다운로드 시 시간이 걸림)
echo "[INFO] Ollama 모델 확인/풀: ${TAG_MODEL}, ${CAT_MODEL}"
ollama show "${TAG_MODEL}" >/dev/null 2>&1 || ollama pull "${TAG_MODEL}"
ollama show "${CAT_MODEL}" >/dev/null 2>&1 || ollama pull "${CAT_MODEL}"

PIPE_PY="${OUT}/_pipeline.py"
cat > "${PIPE_PY}" <<'PYCODE'
from __future__ import annotations
import json, os, sys, pathlib, re
from typing import List, Dict, Any
import pandas as pd
import yake, ollama
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

def extract_keywords_yake(input_jsonl: str, output_jsonl: str, max_keywords: int = 5):
    kw = yake.KeywordExtractor(top=max_keywords, stopwords=None)
    with open(input_jsonl, "r", encoding="utf-8") as fin,\
         open(output_jsonl, "w", encoding="utf-8") as fout:
        for line in fin:
            if not line.strip():
                continue
            obj = json.loads(line)
            text = f"{obj.get('title','')} {obj.get('description','')}".strip()
            obj["keywords"] = [k for k,_ in kw.extract_keywords(text)] if text else []
            fout.write(json.dumps(obj, ensure_ascii=False) + "\n")

CONTROLLED_VOCAB = {
    "org": ["OpenAI","Anthropic","Google","Microsoft","Meta","NVIDIA","Apple","xAI","Amazon","IBM","Mistral","Naver","Samsung"],
    "model": ["GPT-6","Claude-3.7","Llama-4","Gemini-2","Grok","Qwen","Yi","Phi","Mixtral"],
    "domain": ["Healthcare","Fintech","Education","Robotics","AutonomousVehicle","Gaming","Security","Search","Cloud"],
    "topic": ["Multimodal","RAG","Agent","Safety","Benchmark","Compression","Distillation","MoE","ScalingLaw"],
    "event": ["Funding","Acquisition","IPO","Partnership","Layoff","Conference","Launch","Outage"],
    "geo": ["US","EU","KR","CN","JP","UK"],
    "biz": ["Pricing","Monetization","GoToMarket","Ecosystem","OpenSource"],
    "policy": ["Regulation","ExportControl","Standard","Guideline","Subsidy","RFP"],
}

def _vocab_text():
    rows=[]
    for k,vals in CONTROLLED_VOCAB.items():
        for v in vals:
            rows.append(f"{k}/{v}")
    return ", ".join(rows)

PROMPT_TAG = """You are an expert tagger for AI-related articles. Only output comma-separated tags in 'prefix/Value'.
Allowed prefixes: org, model, domain, topic, event, geo, biz, policy.
Use the controlled vocabulary when applicable; otherwise propose a reasonable new tag under the right prefix.
Controlled vocabulary: {vocab}
YAKE keywords: {yake}
Article:
Title: {title}
Content: {content}
Output only the tags, no extra text:
"""

def _clean_tag(tag: str) -> str | None:
    tag = tag.strip()
    if not tag or "/" not in tag:
        return None
    if any(c in tag for c in ["*", ":", "**"]):
        return None
    parts = tag.split("/")
    if len(parts) < 2:
        return None
    tag = f"{parts[0].strip()}/{parts[1].strip()}"
    tag = tag.replace(" ", "")
    fixes = {"biz/Regulation":"policy/Regulation","event/NA":"event/Unknown"}
    return fixes.get(tag, tag)

def _gen_tags_ollama(title, content, keywords, model):
    prompt = PROMPT_TAG.format(
        vocab=_vocab_text(),
        yake=", ".join(keywords or []),
        title=title or "",
        content=content or ""
    )
    try:
        resp = ollama.chat(model=model, messages=[{"role":"user","content":prompt}])
        raw = resp["message"]["content"].strip()
        tags = [t.strip() for t in raw.split(",") if t.strip()]
        cleaned = []
        for t in tags:
            c = _clean_tag(t)
            if c and any(c.startswith(p+"/") for p in CONTROLLED_VOCAB.keys()):
                cleaned.append(c)
        seen=set(); out=[]
        for t in cleaned:
            if t not in seen:
                seen.add(t); out.append(t)
        return out
    except Exception as e:
        print("Ollama error (tagging):", e, file=sys.stderr)
        return []

def tag_jsonl(input_jsonl: str, output_jsonl: str, model: str, batch_size=5, max_workers=2):
    with open(input_jsonl,"r",encoding="utf-8") as f:
        items=[json.loads(l) for l in f if l.strip()]
    batches=[items[i:i+batch_size] for i in range(0,len(items),batch_size)]
    results=[]
    def _proc(batch):
        out=[]
        for it in tqdm(batch, desc="Tagging", leave=False):
            out.append({**it, "tags": _gen_tags_ollama(it.get("title"), it.get("description"), it.get("keywords"), model)})
        return out
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs={ex.submit(_proc,b):b for b in batches}
        for fut in tqdm(as_completed(futs), total=len(futs), desc="Batches"):
            results.extend(fut.result())
    with open(output_jsonl,"w",encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False)+"\n")

PROMPT_CAT = """You are a professional AI news analyst. Classify each article into exactly ONE of:
1) Research, 2) Technology & Product, 3) Market & Corporate, 4) Policy & Regulation, 5) Society & Culture, 6) Incidents & Safety.
Use title, abstract(content), and keywords. Output ONLY the final label text (no explanations).
Article:
Title: {title}
Abstract: {abstract}
Keywords: {keywords}
Answer:
"""

def classify_jsonl(input_jsonl: str, output_jsonl: str, model: str):
    # 스트리밍 처리로 메모리 절약
    with open(input_jsonl, "r", encoding="utf-8") as fin,\
         open(output_jsonl, "w", encoding="utf-8") as fout:
        for line in tqdm(fin, desc="Classify"):
            if not line.strip():
                continue
            obj = json.loads(line)
            prompt = PROMPT_CAT.format(
                title=obj.get("title",""),
                abstract=obj.get("description",""),
                keywords=", ".join(obj.get("keywords") or []),
            )
            try:
                resp = ollama.chat(model=model, messages=[{"role":"user","content":prompt}])
                label = resp["message"]["content"].strip()
            except Exception as e:
                print("Ollama error (classify):", e, file=sys.stderr)
                label = "Uncategorized"
            obj["category"] = label
            fout.write(json.dumps(obj, ensure_ascii=False) + "\n")

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--inp", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--tag_model", required=True)
    ap.add_argument("--cat_model", required=True)
    ap.add_argument("--max_workers", type=int, default=2)
    ap.add_argument("--max_keywords", type=int, default=5)
    ap.add_argument("--batch_size", type=int, default=5)
    args = ap.parse_args()

    outdir = pathlib.Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    p_keywords = str(outdir / "all_entries_keywords.jsonl")
    p_tags = str(outdir / "all_entries_tags.jsonl")
    p_cats = str(outdir / "all_entries_categories.jsonl")

    print("[1/3] YAKE keywords ->", p_keywords)
    extract_keywords_yake(args.inp, p_keywords, max_keywords=args.max_keywords)

    print("[2/3] Ollama tags ->", p_tags)
    tag_jsonl(p_keywords, p_tags, model=args.tag_model, batch_size=args.batch_size, max_workers=args.max_workers)

    print("[3/3] Ollama category ->", p_cats)
    classify_jsonl(p_keywords, p_cats, model=args.cat_model)

    print("[DONE]", p_keywords, p_tags, p_cats)

if __name__ == "__main__":
    main()
PYCODE

# 실행
python3 "${PIPE_PY}" \
  --inp "${IN}" \
  --outdir "${OUT}" \
  --tag_model "${TAG_MODEL}" \
  --cat_model "${CAT_MODEL}" \
  --max_workers "${MAX_WORKERS}" \
  --max_keywords "${MAX_KEYWORDS}" \
  --batch_size "${BATCH_SIZE}"

echo "[OK] 출력 디렉토리: ${OUT}"
"""

# Write the script file
with open(script_path, "w", encoding="utf-8") as f:
    f.write(script)

# Make it executable
st = os.stat(script_path)
os.chmod(script_path, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

script_path

# bash rss_yake_tag_cate.sh \
#   -i /mnt/data/all_entries_20250825_025249.jsonl \
#   -o /mnt/data/out \
#   -t "gemma3:4b" \
#   -c "gemma3:4b" \
#   -w 2 -k 5 -b 5

