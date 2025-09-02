#!/usr/bin/env python3
"""
원격 Ollama 서버로 태그 추출 + 정제 테스트
"""

from app.services.extract_tags import get_tags_with_ollama, controlled_vocab
from app.services.mongo_simple import mongo
from app.services.tag_cleaner import clean_tags_entry  # ⬅️ 추가


def test_remote_tagging():
    """원격 서버로 태그 추출 및 정제 테스트"""
    print("=== 원격 Ollama 서버 태그 추출 + 정제 테스트 ===")
    
    # 처리된 엔트리 중 하나 가져오기
    entries = mongo.get_rss_entries(limit=1, filter_dict={'processed': True})
    
    if not entries:
        print("❌ 처리된 엔트리가 없습니다.")
        return
    
    entry = entries[0]
    title = entry.get('title', '')
    content = entry.get('description', '')
    keywords = entry.get('keywords', [])
    
    print(f"📄 테스트 엔트리:")
    print(f"   Title: {title}")
    print(f"   Content: {content[:100]}...")
    print(f"   기존 키워드: {keywords[:5]}")
    
    # 다양한 모델로 테스트
    models = [
        "qwen2.5:3b-instruct-q4_K_M",
        "llama3.2:3b-instruct-q5_K_M", 
        "phi3.5:latest",
        "gemma3:4b"
    ]
    
    for model in models:
        print(f"\n🤖 모델: {model}")
        try:
            raw_tags = get_tags_with_ollama(
                title=title,
                content=content,
                yake_keywords=keywords[:5],
                vocab=controlled_vocab,
                model_name=model,
                server_name="remote"
            )
            
            if raw_tags:
                # ✅ 정제 과정 추가
                cleaned_tags = clean_tags_entry(raw_tags)
                print(f"🟡 원본 태그 ({len(raw_tags)}개): {raw_tags}")
                print(f"✅ 정제된 태그 ({len(cleaned_tags)}개): {cleaned_tags}")
            else:
                print("⚠️ 태그가 추출되지 않았습니다.")
                
        except Exception as e:
            print(f"❌ 오류: {e}")


if __name__ == "__main__":
    test_remote_tagging()
