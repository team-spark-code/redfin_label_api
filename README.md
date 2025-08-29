# RedFin Label API

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.112+-green.svg)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://www.docker.com/)

키워드 추출(YAKE), 태그/카테고리 분류(LLM)를 제공하는 AI 텍스트 분석 API 서비스

## 1. 개요

RedFin Label API는 AI 산업 뉴스의 키워드 추출, 태그 생성, 카테고리 분류를 위한 AI 텍스트 분석 서비스입니다. YAKE 알고리즘과 Ollama LLM을 활용하여 정확하고 빠른 텍스트 분석을 제공하며, RedFin 서비스의 데이터 처리 파이프라인에서 핵심 역할을 담당합니다.

## 2. 주요 기능

- **키워드 추출**: YAKE 알고리즘을 사용한 자동 키워드 추출
- **태그 생성**: Ollama LLM을 활용한 지능형 태그 생성
- **카테고리 분류**: MINDS-2025 스키마 기반 다중 라벨 분류
- **배치 처리**: 대용량 텍스트 데이터의 효율적 처리
- **RESTful API**: 표준 HTTP 인터페이스
- **MongoDB 지원**: 결과 저장 및 조회

## 3. 빠른 시작

### 3.1 Docker Compose (권장)

```bash
# 저장소 클론
git clone <repository-url>
cd redfin_label_api

# 전체 스택 실행 (API + Ollama + MongoDB)
docker-compose up -d

# API 테스트
curl http://localhost:8010/api/v1/health
```

### 3.2 로컬 설치

```bash
# 저장소 클론
git clone <repository-url>
cd redfin_label_api

# 가상환경 설정
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# 의존성 설치
pip install -r requirements.txt

# 환경 변수 설정
cp .env.example .env

# Ollama 설치 및 모델 다운로드
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull gemma2:2b
ollama serve &

# 서버 실행
python main.py
```

## 4. API 문서

- **Swagger UI**: http://localhost:8010/docs
- **ReDoc**: http://localhost:8010/redoc
- **API 루트**: http://localhost:8010/

## 5. 핵심 API 엔드포인트

### 5.1 텍스트 분석
```http
POST /api/v1/extract
```

**요청 예시:**
```json
{
  "texts": [
    {
      "id": "doc-001",
      "title": "AI Breakthrough in Natural Language Processing",
      "content": "Researchers have achieved a major breakthrough...",
      "lang": "en"
    }
  ],
  "options": {
    "keywords": {"enable": true, "top_k": 10},
    "tags": {"enable": true, "top_k": 8},
    "categories": {"enable": true, "threshold": 0.30}
  }
}
```

### 5.2 헬스체크
```http
GET /api/v1/health
```

### 5.3 배치 작업
```http
POST   /api/v1/jobs                    # 배치 작업 생성
GET    /api/v1/jobs/{job_id}           # 작업 상태 조회
GET    /api/v1/jobs/{job_id}/results   # 작업 결과 조회
```

## 6. 사용 예시

### 6.1 Python 클라이언트

```python
import requests

def analyze_text(text_content, title=""):
    payload = {
        "texts": [{
            "id": "sample-001",
            "title": title,
            "content": text_content,
            "lang": "en"
        }],
        "options": {
            "keywords": {"enable": True, "top_k": 10},
            "tags": {"enable": True, "top_k": 8},
            "categories": {"enable": True, "threshold": 0.30}
        }
    }
    
    response = requests.post("http://localhost:8010/api/v1/extract", json=payload)
    return response.json()

# 사용 예시
result = analyze_text("AI has made significant progress...", "AI Progress")
print(result)
```

### 6.2 cURL 사용

```bash
# 헬스체크
curl http://localhost:8010/api/v1/health

# 텍스트 분석
curl -X POST http://localhost:8010/api/v1/extract \
  -H "Content-Type: application/json" \
  -d '{
    "texts": [{
      "id": "test-001",
      "title": "Test Article",
      "content": "This is a test article about AI.",
      "lang": "en"
    }],
    "options": {
      "keywords": {"enable": true, "top_k": 5},
      "tags": {"enable": true, "top_k": 3},
      "categories": {"enable": true, "threshold": 0.30}
    }
  }'
```

## 7. Docker 사용법

### 7.1 단일 컨테이너
```bash
# 이미지 빌드
docker build -t redfin-label-api .

# 컨테이너 실행
docker run -p 8010:8010 redfin-label-api
```

### 7.2 전체 스택
```bash
# 모든 서비스 실행 (API + Ollama + MongoDB)
docker-compose up -d

# 서비스 상태 확인
docker-compose ps
```

## 8. 프로젝트 구조

```
redfin_label_api/
├── app/                          # 애플리케이션 코드
│   ├── api.py                   # 통합 API 라우터
│   ├── models.py                # Pydantic 모델
│   ├── services/                # 비즈니스 로직
│   │   ├── extract_category.py  # 카테고리 분류
│   │   ├── extract_keywords.py  # 키워드 추출
│   │   ├── extract_tags.py      # 태그 생성
│   │   └── mongo_simple.py      # MongoDB 연동
│   └── core/                    # 설정 및 의존성
├── data/                        # 데이터 파일
├── tests/                       # 테스트 파일
├── main.py                      # FastAPI 앱 진입점
├── requirements.txt             # Python 의존성
├── Dockerfile                   # Docker 이미지 설정
├── docker-compose.yaml          # 컨테이너 오케스트레이션
└── README.md                    # 프로젝트 문서
```

## 9. 개발

### 9.1 개발 환경 설정
```bash
# 개발 의존성 설치
pip install -r requirements.txt

# 코드 포맷팅
black app/ tests/
isort app/ tests/

# 테스트 실행
pytest tests/ -v
```

### 9.2 테스트
```bash
# 단위 테스트
pytest

# API 테스트
python test_ollama_models.py
python test_remote_tags.py
```

## 10. 문제 해결

### 10.1 Ollama 연결 오류
```bash
# Ollama 서비스 상태 확인
ollama list

# 모델 재다운로드
ollama pull gemma2:2b

# Ollama 서버 재시작
pkill ollama && ollama serve
```

### 10.2 MongoDB 연결 오류
```bash
# MongoDB 서비스 상태 확인
sudo systemctl status mongodb

# MongoDB 연결 테스트
mongosh mongodb://localhost:27017
```

## 11. 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다.

## 12. 지원

- **Issues**: [GitHub Issues](https://github.com/your-username/redfin_label_api/issues)
- **Documentation**: http://localhost:8010/docs

---

**RedFin Label API** - AI 기반 텍스트 분석 서비스
