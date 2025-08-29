#!/usr/bin/env python3
"""
Ollama 모델 테스트 및 설정 확인 스크립트
"""

from app.services.extract_tags import get_ollama_client, get_available_models, get_tags_with_ollama, controlled_vocab
from app.core.config import settings


def test_server_connection(server_name: str):
    """서버 연결 테스트"""
    print(f"\n=== {server_name} 서버 연결 테스트 ===")
    
    try:
        client, server_config = get_ollama_client(server_name)
        print(f"✅ 서버 연결 성공: {server_config['base_url']}")
        
        # 간단한 ping 테스트
        available_models = list(server_config.get("models", {}).keys())
        if available_models:
            test_model = available_models[0]
            print(f"🔍 테스트 모델: {test_model}")
            
            response = client.chat(
                model=test_model,
                messages=[{"role": "user", "content": "Say 'Hello' in one word."}]
            )
            result = response['message']['content'].strip()
            print(f"✅ 응답: {result}")
            return True
        else:
            print("❌ 사용 가능한 모델이 없습니다.")
            return False
            
    except Exception as e:
        print(f"❌ 서버 연결 실패: {e}")
        return False


def test_tag_extraction(server_name: str, model_name: str):
    """태그 추출 테스트"""
    print(f"\n=== 태그 추출 테스트: {server_name}/{model_name} ===")
    
    # 테스트 텍스트
    title = "OpenAI releases new GPT model"
    content = "OpenAI has announced the release of a new language model that improves on previous versions with better reasoning capabilities and safety features."
    keywords = ["OpenAI", "GPT", "language model", "reasoning", "safety"]
    
    try:
        tags = get_tags_with_ollama(
            title=title,
            content=content,
            yake_keywords=keywords,
            vocab=controlled_vocab,
            model_name=model_name,
            server_name=server_name
        )
        
        print(f"✅ 추출된 태그 ({len(tags)}개): {tags}")
        return True
        
    except Exception as e:
        print(f"❌ 태그 추출 실패: {e}")
        return False


def show_configuration():
    """현재 설정 표시"""
    print("=== 현재 Ollama 설정 ===")
    print(f"기본 서버: {settings.DEFAULT_OLLAMA_SERVER}")
    print(f"기본 모델: {settings.DEFAULT_OLLAMA_MODEL}")
    
    print("\n=== 사용 가능한 서버 및 모델 ===")
    for server_name, config in settings.OLLAMA_SERVERS.items():
        print(f"\n📍 {server_name}:")
        print(f"   URL: {config['base_url']}")
        print(f"   모델들:")
        for model in config.get("models", {}):
            print(f"     - {model}")


def main():
    """메인 테스트 함수"""
    show_configuration()
    
    # 각 서버 연결 테스트
    working_servers = []
    for server_name in settings.OLLAMA_SERVERS.keys():
        if test_server_connection(server_name):
            working_servers.append(server_name)
    
    print(f"\n=== 연결 가능한 서버: {working_servers} ===")
    
    # 작동하는 서버에서 태그 추출 테스트
    for server_name in working_servers:
        server_config = settings.OLLAMA_SERVERS[server_name]
        models = list(server_config.get("models", {}).keys())
        
        if models:
            # 첫 번째 모델로 테스트
            model_name = models[0]
            test_tag_extraction(server_name, model_name)
    
    print("\n=== 권장 설정 ===")
    if working_servers:
        recommended_server = working_servers[0]
        server_config = settings.OLLAMA_SERVERS[recommended_server]
        recommended_model = list(server_config.get("models", {}).keys())[0]
        
        print(f"✅ 권장 서버: {recommended_server}")
        print(f"✅ 권장 모델: {recommended_model}")
        print(f"\n사용 명령어:")
        print(f"python process_all_rss.py --use-tags --ollama-server {recommended_server} --ollama-model {recommended_model}")
    else:
        print("❌ 작동하는 Ollama 서버가 없습니다.")


if __name__ == "__main__":
    main()
