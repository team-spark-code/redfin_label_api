"""
MongoDB service
"""
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from typing import Dict, List, Any, Generator, Optional
import logging

from ..core.config import settings

logger = logging.getLogger(__name__)


class MongoService:
    """MongoDB 서비스"""
    
    def __init__(self, connection_string: Optional[str] = None):
        self.connection_string = connection_string or settings.MONGO_SERVERS['local']['base_url']
        self.client = None
        self._connect()
    
    def _connect(self):
        """MongoDB 연결"""
        try:
            self.client = MongoClient(
                self.connection_string,
                serverSelectionTimeoutMS=5000,  # 5초 타임아웃
                connectTimeoutMS=5000,
                socketTimeoutMS=5000
            )
            # 연결 테스트
            self.client.admin.command('ping')
            logger.info(f"MongoDB 연결 성공: {self.connection_string}")
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error(f"MongoDB 연결 실패: {e}")
            self.client = None
    
    def get_database(self, db_name: str = None):
        """데이터베이스 반환"""
        if not self.client:
            self._connect()
        
        db_name = db_name or settings.MONGO_DB
        return self.client[db_name] if self.client else None
    
    def get_documents(self, collection_name: str, limit: int = 10, db_name: str = None) -> List[Dict[str, Any]]:
        """문서들 가져오기"""
        db = self.get_database(db_name)
        if db is None:
            return []
        
        collection = db[collection_name]
        return list(collection.find().limit(limit))
    
    def update_document(self, collection_name: str, doc_id: Any, update_data: Dict[str, Any], db_name: str = None):
        """문서 업데이트"""
        from bson import ObjectId
        
        db = self.get_database(db_name)
        if db is None:
            return None
        
        collection = db[collection_name]
        
        # ObjectId 변환 처리
        if isinstance(doc_id, str):
            try:
                doc_id = ObjectId(doc_id)
            except:
                pass  # 문자열 ID 그대로 사용
        
        result = collection.update_one(
            {"_id": doc_id}, 
            {"$set": update_data}
        )
        
        return result
    
    def stream_docs(self, uri: str, db: str, collection: str, 
                   flt: Dict[str, Any] = None, 
                   proj: Dict[str, Any] = None, 
                   batch_size: int = 100) -> Generator[Dict[str, Any], None, None]:
        """문서 스트림으로 가져오기 (배치 처리용)"""
        try:
            client = MongoClient(uri, serverSelectionTimeoutMS=5000)
            database = client[db]
            coll = database[collection]
            
            cursor = coll.find(flt or {}, proj or {}).batch_size(batch_size)
            for doc in cursor:
                # ObjectId를 문자열로 변환
                if '_id' in doc:
                    doc['_id'] = str(doc['_id'])
                yield doc
                
        except Exception as e:
            logger.error(f"MongoDB 스트림 오류: {e}")
            return
        finally:
            if 'client' in locals():
                client.close()
    
    def ping(self, uri: str, db: str, collection: str) -> Dict[str, Any]:
        """MongoDB 연결 테스트"""
        try:
            client = MongoClient(uri, serverSelectionTimeoutMS=5000)
            database = client[db]
            coll = database[collection]
            
            # 연결 테스트
            client.admin.command('ping')
            count = coll.count_documents({})
            
            return {
                "status": "success",
                "message": f"연결 성공: {db}.{collection}",
                "document_count": count
            }
        except Exception as e:
            return {
                "status": "error", 
                "message": f"연결 실패: {str(e)}"
            }
        finally:
            if 'client' in locals():
                client.close()
    
    def get_rss_entries(self, limit: int = 100, skip: int = 0, 
                       filter_dict: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """RSS 엔트리 가져오기"""
        from bson import ObjectId
        
        db = self.get_database()
        if db is None:
            return []
        
        collection = db[settings.MONGO_COLLECTION]
        
        # 필터에서 _id 처리
        if filter_dict and '_id' in filter_dict:
            filter_id = filter_dict['_id']
            if isinstance(filter_id, str):
                try:
                    filter_dict['_id'] = ObjectId(filter_id)
                except:
                    pass
        
        cursor = collection.find(filter_dict or {}).skip(skip).limit(limit)
        
        results = []
        for doc in cursor:
            # ObjectId를 문자열로 변환
            if '_id' in doc:
                doc['_id'] = str(doc['_id'])
            results.append(doc)
        
        return results
    
    def count_rss_entries(self, filter_dict: Dict[str, Any] = None) -> int:
        """RSS 엔트리 개수 반환"""
        db = self.get_database()
        if db is None:
            return 0
        
        collection = db[settings.MONGO_COLLECTION]
        return collection.count_documents(filter_dict or {})


# 인스턴스 생성
mongo = MongoService()
