#!/usr/bin/env python3
"""
Ollama 서버 준비 대기 및 테스트
"""

import time
import requests
from app.services.extract_tags import get_ollama_client


def wait_for_ollama(max_wait=60):
    """Ollama 서버가 준비될 때까지 대기"""
    print("=== Ollama 서버 연결 대기 중 ===")
    
    for i in range(max_wait):
        try:
            response = requests.get("http://100.97.183.123:11434/api/version", timeout=5)
            if response.status_code == 200:
                print(f"✅ {i+1}초 후 연결 성공!")
                print(f"   Ollama 버전: {response.json()}")
                return True
        except:
            pass
        
        print(f"⏳ 대기 중... ({i+1}/{max_wait})")
        time.sleep(1)
    
    print("❌ 연결 시간 초과")
    return False


if __name__ == "__main__":
    if wait_for_ollama():
        print("\n🎉 이제 태그 추출 테스트를 실행할 수 있습니다!")
        print("python test_remote_tags.py")
    else:
        print("\n⚠️  Ollama 서버 설정을 확인해주세요.")
