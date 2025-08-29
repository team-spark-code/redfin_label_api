"""
AI-powered article classification service
"""
import json
import re
from typing import Dict, Any, Optional
import ollama


class ArticleClassifier:
    """AI 기반 기사 분류 서비스"""
    
    def __init__(self, model: str = "gemma3:4b"):
        self.model = model
        self.categories = [
            "Research",
            "Technology & Product", 
            "Market & Corporate",
            "Policy & Regulation",
            "Society & Culture",
            "Incidents & Safety"
        ]
    
    def _build_classification_prompt(self, title: str, description: str, keywords: str = "") -> str:
        """분류를 위한 프롬프트 생성"""
        
        article_text = f"""
Title: "{title}"
Abstract: "{description}"
Keywords: "{keywords}"
"""
        
        prompt = f"""
You are a professional news analyst. 
Your task is to classify this news article into **exactly one primary category** 
out of the six predefined categories below. 

Use the **title**, **abstract**, and **keywords** to decide, 
and follow the **priority rules** when multiple aspects are present.  

---

### Categories and Rules:

1. Research (학술)
- 포함: 논문, 프리프린트, 학회 채택/수상, 벤치마크·데이터셋 공개.
- 제외: 제품 릴리스 노트(→ Technology).
- 경계 규칙: "학회/논문 성과가 리드"면 Research 우선.

2. Technology & Product (기술/제품)
- 포함: 모델/제품 릴리스, 성능 업데이트, 모델 카드/리드미 변경, 기능 개선.
- 제외: 자금/거래 중심 기사(→ Market & Corporate).
- 경계 규칙: "연구 성과"보다 "제품·기능" 전달이 리드면 여기.

3. Market & Corporate (시장/기업)
- 포함: 투자·M&A·IPO·실적, 리더십/조직개편, 제휴·상용화 계약, 상업 로드맵.
- 제외: 공공 규제·지원(→ Policy & Regulation).
- 경계 규칙: 금액·거래·실적·지배구조가 리드면 여기.

4. Policy & Regulation (정책/규제)
- 포함: 법·규제·가이드라인, 공공자금(보조금·RFP), 수출통제, 표준화·거버넌스.
- 제외: 기업 자체 정책(가격·상업 전략, → Market & Corporate).
- 경계 규칙: 공공 주체의 룰/지원이 핵심이면 여기.

5. Society & Culture (사회/문화)
- 포함: 대중 활용 트렌드, 창작·교육·밈, 저작권/윤리 공론의 사회적 논의(정책화 전 단계).
- 제외: 순수 기술 업데이트(→ Technology), 입법·규제(→ Policy).
- 경계 규칙: "사회적 파급·수용"이 리드면 여기.

6. Incidents & Safety (사건/안전/운영)
- 포함: 서비스 장애, 보안 사고/유출, 모델 오남용/중대한 안전 이슈, 리콜/중단.
- 제외: 일반 제품 릴리스(→ Technology), 법·제재(→ Policy).
- 경계 규칙: "사건/사건/리스크 대응"이 중심이면 여기.

---

### Priority Rules (apply in order if overlaps):
1. Incidents & Safety
2. Policy & Regulation
3. Market & Corporate
4. Research
5. Technology & Product
6. Society & Culture

---

### Output format:
Return ONLY a valid JSON object, with no extra text, like this:
{{"category": "Research", "confidence": 0.85, "reasoning": "This article discusses academic research findings"}}

Here is the article:
{article_text}
"""
        return prompt
    
    def classify_article(self, title: str, description: str, keywords: str = "") -> Dict[str, Any]:
        """
        단일 기사 분류
        
        Args:
            title: 기사 제목
            description: 기사 요약/설명
            keywords: 키워드 (선택사항)
            
        Returns:
            Dict[str, Any]: 분류 결과
        """
        try:
            prompt = self._build_classification_prompt(title, description, keywords)
            
            # Ollama API 호출
            response = ollama.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}]
            )
            
            content = response["message"]["content"].strip()
            
            # JSON 파싱 시도
            try:
                result = json.loads(content)
                category = result.get("category", "Uncategorized")
                confidence = result.get("confidence", 0.0)
                reasoning = result.get("reasoning", "")
                
                # 카테고리 유효성 검사
                if category not in self.categories:
                    category = "Uncategorized"
                    confidence = 0.0
                    reasoning = f"Invalid category returned: {category}"
                
                return {
                    "category": category,
                    "confidence": confidence,
                    "reasoning": reasoning,
                    "success": True
                }
                
            except json.JSONDecodeError:
                # 정규식으로 카테고리 추출 시도
                category_match = re.search(r'"category"\s*:\s*"([^"]+)"', content)
                if category_match:
                    category = category_match.group(1)
                    if category in self.categories:
                        return {
                            "category": category,
                            "confidence": 0.5,  # 기본값
                            "reasoning": "Extracted from partial response",
                            "success": True
                        }
                
                # 실패 시 기본값 반환
                return {
                    "category": "Uncategorized",
                    "confidence": 0.0,
                    "reasoning": f"Failed to parse AI response: {content[:100]}...",
                    "success": False
                }
                
        except Exception as e:
            return {
                "category": "Uncategorized",
                "confidence": 0.0,
                "reasoning": f"Classification error: {str(e)}",
                "success": False
            }
    
    def get_available_categories(self) -> list[str]:
        """사용 가능한 카테고리 목록 반환"""
        return self.categories.copy()


# 싱글톤 인스턴스
classifier = ArticleClassifier()
