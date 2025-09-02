from dotenv import load_dotenv ; load_dotenv()
import json
import ollama
from ..core.config import settings

# 제한어 목록 (Controlled vocabulary)
controlled_vocab = {
    'org': ['OpenAI', 'Anthropic', 'Naver', 'Google', 'Microsoft', 'NVIDIA', 'MIT', 'Facebook', 'Apple', 'Intel', 'Sony', 'Honeywell', 'Oracle', 'SenseTime'],
    'model': ['GPT-6', 'Claude-3.7', 'Genie', 'Assistant', 'Azure', 'Mini Cheetah', 'Smart Compose'],
    'domain': ['Healthcare', 'Fintech', 'Education', 'Transportation', 'Robotics'],
    'topic': ['Multimodal', 'RAG', 'Agents', 'Safety', 'Robotics'],
    'event': ['NeurIPS2025', 'GoogleIO', 'WWDC', 'MAX'],
    'geo': ['KR', 'US', 'EU', 'CN'],
    'biz': ['M&A', 'Funding', 'Earnings', 'Pricing', 'Hiring'],
    'policy': ['Regulation', 'Standard', 'Grant']
}

def get_ollama_client(server_name: str = None, model_name: str = None):
    """Ollama 클라이언트 설정"""
    server_name = server_name or settings.DEFAULT_OLLAMA_SERVER
    server_config = settings.OLLAMA_SERVERS.get(server_name)
    
    if not server_config:
        raise ValueError(f"Unknown server: {server_name}")
    
    base_url = server_config["base_url"]
    
    # 원격 서버인 경우 클라이언트 설정
    if "localhost" not in base_url and "127.0.0.1" not in base_url:
        client = ollama.Client(host=base_url)
    else:
        client = ollama
    
    return client, server_config


def get_available_models(server_name: str = None):
    """사용 가능한 모델 목록 반환"""
    server_name = server_name or settings.DEFAULT_OLLAMA_SERVER
    server_config = settings.OLLAMA_SERVERS.get(server_name, {})
    return list(server_config.get("models", {}).keys())


def get_tags_with_ollama(title, content, yake_keywords, vocab, 
                        model_name=None, server_name=None):
    """원격 Ollama 서버 지원하는 태그 추출"""
    
    # 기본값 설정
    server_name = server_name or settings.DEFAULT_OLLAMA_SERVER
    model_name = model_name or settings.DEFAULT_OLLAMA_MODEL
    
    # 모델명에서 'ollama:' 접두어 제거
    if model_name.startswith("ollama:"):
        model_name = model_name.replace("ollama:", "")
    
    vocab_text = "\n".join([f"{k}: {', '.join(v)}" for k, v in vocab.items()])
    yake_text = ", ".join(yake_keywords)

    prompt = f"""
You are an expert tagger for AI-related articles. Your task is to generate relevant tags in the format 'category/keyword' based on the provided controlled vocabulary and YAKE keywords.

**Controlled Vocabulary**:
{vocab_text}

**YAKE Keywords**:
{yake_text}

**Rules**:
1. Prioritize tags from the controlled vocabulary when the title or content matches exactly or closely.
2. If a YAKE keyword or content term doesn't match the vocabulary but is relevant, propose a new tag within allowed categories.
3. Capitalize keywords in tags for consistency.
4. Output only comma-separated tags in 'category/Keyword'.

**Article**:
Title: {title}
Content: {content}

**Output**:
"""
    try:
        client, server_config = get_ollama_client(server_name)
        
        # 모델이 서버에서 사용 가능한지 확인
        available_models = server_config.get("models", {})
        if model_name not in available_models:
            print(f"Warning: Model {model_name} not found on {server_name}, using first available")
            model_name = next(iter(available_models.keys())) if available_models else "gemma3:4b"
        
        print(f"Using Ollama server: {server_config['base_url']}, model: {model_name}")
        
        response = client.chat(
            model=model_name, 
            messages=[{"role": "user", "content": prompt}]
        )
        raw_tags = response['message']['content'].strip()
        tag_list = [t.strip() for t in raw_tags.split(",") if t.strip()]
        return tag_list
        
    except Exception as e:
        print(f"Error calling Ollama ({server_name}/{model_name}): {e}")
        return []


# 하위 호환성을 위한 기존 함수명 유지
def get_tags_with_ollama_legacy(title, content, yake_keywords, vocab, model_name="gemma3:4b"):
    """기존 호환성을 위한 래퍼 함수"""
    return get_tags_with_ollama(title, content, yake_keywords, vocab, model_name)


# simple_processor 호환용
def extract_tags_from_text(text: str, top_k: int = 8, model_name: str = None, server_name: str = None):
    """
    단일 문자열 입력으로 YAKE 키워드를 내부에서 뽑아 Ollama 태깅을 수행하는 헬퍼
    (simple_processor 호환용)
    """
    text = (text or "").strip()
    # YAKE로 보조 키워드 생성
    try:
        import yake
        kw_extractor = yake.KeywordExtractor(top=top_k, stopwords=None)
        yake_keywords = [kw for kw, _ in kw_extractor.extract_keywords(text)]
    except Exception:
        yake_keywords = []

    # 제목은 비워두고 content에만 본문을 둠
    tags = get_tags_with_ollama(
        title="",
        context=text,
        yake_keywords=yake_keywords,
        vocab=controlled_vocab,
        model_name=model_name,
        server_name=server_name
    )
    return tags
