import json
import logging
from typing import List, Dict
from elasticsearch import Elasticsearch, helpers
from sentence_transformers import SentenceTransformer
from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class Article(BaseModel):
    guid: str
    title: str
    description: str = ""
    keywords: List[str] = []

class ArticleService:
    def __init__(self, es_host: str, es_auth: tuple, index_name: str):
        """Initialize Elasticsearch client and SentenceTransformer model."""
        self.index_name = index_name
        try:
            self.es = Elasticsearch(
                es_host,
                basic_auth=es_auth,
                verify_certs=False,
                request_timeout=30
            )
            info = self.es.info()
            logger.info(f"Connected to Elasticsearch: {info['cluster_name']}")
        except Exception as e:
            logger.error(f"Elasticsearch connection failed: {e}")
            raise

        try:
            self.model = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("Loaded SentenceTransformer model")
        except Exception as e:
            logger.error(f"Failed to load SentenceTransformer model: {e}")
            raise

    def load_jsonl_data(self, file_path: str) -> List[Dict]:
        """Load JSONL data with robust error handling."""
        articles = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    articles = data
                elif isinstance(data, dict):
                    articles = [data]
                else:
                    raise ValueError("Unexpected data structure")
                logger.info("Loaded as single JSON array")
        except json.JSONDecodeError as e:
            logger.warning(f"Single JSON load failed: {e}. Falling back to JSONL parsing.")
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_number, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        logger.debug(f"Line {line_number}: Skipping empty line")
                        continue
                    try:
                        articles.append(json.loads(line))
                    except json.JSONDecodeError:
                        logger.error(f"Line {line_number}: Skipping invalid line: {line[:100]}...")
                        continue
        logger.info(f"Loaded {len(articles)} articles from {file_path}")
        return articles

    def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for the given text."""
        try:
            embedding = self.model.encode(text).tolist()
            logger.debug(f"Generated embedding for text (length: {len(embedding)})")
            return embedding
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            return []

    def create_index(self):
        """Create Elasticsearch index if it doesn't exist."""
        try:
            if not self.es.indices.exists(index=self.index_name):
                self.es.indices.create(
                    index=self.index_name,
                    body={
                        "mappings": {
                            "properties": {
                                "guid": {"type": "keyword"},
                                "title": {"type": "text"},
                                "description": {"type": "text"},
                                "keywords": {"type": "text"},
                                "embedding": {
                                    "type": "dense_vector",
                                    "dims": 384
                                }
                            }
                        }
                    }
                )
                logger.info(f"Created Elasticsearch index: {self.index_name}")
            else:
                logger.info(f"Index {self.index_name} already exists")
        except Exception as e:
            logger.error(f"Failed to create index {self.index_name}: {e}")
            raise

    def index_articles(self, articles: List[Dict], chunk_size: int = 100) -> int:
        """Index articles to Elasticsearch in chunks."""
        def generate_actions(articles_chunk: List[Dict]):
            for article in articles_chunk:
                guid = article.get("guid")
                title = article.get("title", "")
                description = article.get("description", "")
                keywords = ", ".join(article.get("keywords", [])) if article.get("keywords") else ""

                if not description or len(description.strip()) < 20:
                    text_for_embedding = f"{title}. {keywords}".strip()
                    logger.warning(f"Short/missing description for GUID {guid}, using title and keywords")
                else:
                    text_for_embedding = f"{title}. {description}. {keywords}".strip()

                embedding = self.generate_embedding(text_for_embedding)
                if not embedding:
                    logger.warning(f"Skipping article with GUID {guid} due to embedding failure")
                    continue

                yield {
                    "_index": self.index_name,
                    "_id": guid,
                    "_source": {
                        "guid": guid,
                        "title": title,
                        "description": description,
                        "keywords": keywords,
                        "embedding": embedding
                    }
                }

        total_indexed = 0
        for i in range(0, len(articles), chunk_size):
            chunk = articles[i:i + chunk_size]
            try:
                success, failed = helpers.bulk(self.es, generate_actions(chunk))
                total_indexed += success
                logger.info(f"Indexed {success} articles in chunk {i//chunk_size + 1}")
                if failed:
                    logger.error(f"Failed to index {len(failed)} articles in chunk {i//chunk_size + 1}")
            except Exception as e:
                logger.error(f"Error indexing chunk {i//chunk_size + 1}: {e}")
        return total_indexed

    def search_recommendations(self, query: str, top_k: int = 5, filters: Dict = None) -> List[Dict]:
        """Search for article recommendations based on a query string."""
        query_embedding = self.generate_embedding(query)
        if not query_embedding:
            logger.error("Failed to generate query embedding")
            return []

        es_query = {
            "query": {
                "script_score": {
                    "query": {"match_all": {}} if not filters else filters,
                    "script": {
                        "source": "cosineSimilarity(params.query_vector, 'embedding') + 1.0",
                        "params": {"query_vector": query_embedding}
                    }
                }
            },
            "size": top_k
        }

        try:
            response = self.es.search(index=self.index_name, body=es_query)
            hits = response['hits']['hits']
            recommendations = [
                {
                    "guid": hit["_id"],
                    "title": hit["_source"]["title"],
                    "description": hit["_source"]["description"],
                    "keywords": hit["_source"]["keywords"],
                    "score": hit["_score"]
                }
                for hit in hits
            ]
            logger.info(f"Retrieved {len(recommendations)} recommendations for query: {query[:50]}...")
            return recommendations
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []