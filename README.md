# Redfin Recommendation API

FastAPI 기반의 태그 분류 및 카테고리화 서비스입니다.

```bash
redfin-tag-categorization/
├── app/
│   ├── api/          # 라우터(REST)
│   ├── services/     # 태깅·카테고리 로직, YAKE/LLM 어댑터
│   ├── schemas/      # Pydantic 모델
│   ├── core/         # 설정(.env, logging), deps
│   └── main.py       # FastAPI 엔트리
├── notebooks/        # 실험용 *.ipynb (배포 경로와 분리)
├── data/
│   ├── input/        # 샘플 입력 (소량만, 대용량은 외부 스토리지)
│   └── output/       # 결과물 (gitignore)
├── tests/
├── requirements.txt  # 또는 pyproject.toml
├── .env.example
├── .gitignore
└── README.md
```

### API (v1)
```bash
GET   /api/v1/health
GET   /api/v1/catalog/categories        # 사용 가능한 카테고리 스키마 목록/내용
GET   /api/v1/catalog/tags              # 사전(있다면)
POST  /api/v1/extract                   # 본문→ {keywords,tags,categories} 통합 추출
POST  /api/v1/jobs                      # 배치 처리(텍스트 배열 or 외부 소스 지정)
GET   /api/v1/jobs/{job_id}             # 상태 조회(queued/running/succeeded/failed)
GET   /api/v1/jobs/{job_id}/results     # 결과 페이지네이션 조회
POST  /api/v1/jobs/{job_id}/cancel
GET   /api/v1/connectors/mongo/test     # 선택: 연결 테스트

# 레거시 호환(필요 시)
POST  /api/v1/categories/classify-article  # 내부적으로 /extract 호출 or 301/307 리다이렉트
```

### POST /extract
```json
{
  "texts": [
    {
      "id": "doc-001",
      "title": "string",
      "content": "string",
      "url": "string",
      "lang": "en"
    }
  ],
  "options": {
    "keywords": {"enable": true, "algo": "yake", "top_k": 10},
    "tags":      {"enable": true, "model": "ollama:gemma2:2b", "top_k": 8},
    "categories":{"enable": true, "scheme": "minds-2025", "multi_label": true, "threshold": 0.30}
  }
}
```

### 응답(요약)
```json
{
  "results": [
    {
      "id": "doc-001",
      "keywords": [{"text": "LLM", "score": 0.92}],
      "tags":      [{"name": "model-updates", "score": 0.88}],
      "categories":[{"name": "AI/기술/모델", "score": 0.81}]
    }
  ],
  "meta": {"model":"ollama:gemma2:2b","algo":"yake"}
}

```