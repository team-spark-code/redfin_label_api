"""
Simple document processor
"""
from typing import Dict, Any
from .mongo_simple import mongo
from .extract_keywords import extract_keywords_from_text
from .extract_tags import extract_tags_from_text  
from .extract_category import classifier


def process_single_document(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    단일 문서 처리
    
    Args:
        doc: MongoDB 문서
        
    Returns:
        Dict: 처리 결과
    """
    title = doc.get("title", "")
    description = doc.get("description", "")
    
    # 1. 키워드 추출
    keywords = extract_keywords_from_text(f"{title} {description}")
    
    # 2. 태그 추출  
    tags = extract_tags_from_text(f"{title} {description}")
    
    # 3. 카테고리 분류
    category_result = classifier.classify_article(title, description)
    
    return {
        "keywords": keywords,
        "tags": tags,
        "category": category_result.get("category"),
        "confidence": category_result.get("confidence", 0.0),
        "processed": True
    }


def process_collection(collection_name: str, limit: int = 10):
    """
    컬렉션 배치 처리
    
    Args:
        collection_name: 처리할 컬렉션 이름
        limit: 처리할 문서 수
    """
    print(f"Processing collection: {collection_name}")
    
    # 문서들 가져오기
    documents = mongo.get_documents(collection_name, limit)
    print(f"Found {len(documents)} documents")
    
    processed_count = 0
    
    for doc in documents:
        try:
            # 이미 처리된 문서는 건너뛰기
            if doc.get("processed"):
                continue
                
            print(f"Processing document: {doc.get('_id')}")
            
            # 문서 처리
            result = process_single_document(doc)
            
            # 결과 저장
            mongo.update_document(collection_name, doc["_id"], result)
            
            processed_count += 1
            print(f"✓ Processed: {doc.get('title', 'No title')[:50]}...")
            
        except Exception as e:
            print(f"✗ Error processing {doc.get('_id')}: {e}")
            # 에러 정보 저장
            mongo.update_document(collection_name, doc["_id"], {
                "processing_error": str(e),
                "processed": False
            })
    
    print(f"Completed. Processed {processed_count} documents.")
