import os
from elasticsearch import Elasticsearch, helpers
from dotenv import load_dotenv
import asyncio
import json
from sentence_transformers import SentenceTransformer
import random
from datetime import datetime # <-- Thêm thư viện thời gian

# --- Phần tải model (Giữ nguyên) ---
try:
    EMBEDDING_MODEL_NAME = os.getenv('MODEL_NAME', 'bkai-foundation-models/vietnamese-bi-encoder') # <-- Dùng model của em
    embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME, device='cpu')
    print(f"✅ Tải mô hình embedding '{EMBEDDING_MODEL_NAME}' thành công.")
except Exception as e:
    print(f"❌ LỖI NGHIÊM TRỌNG: Không thể tải mô hình embedding: {e}")
    embedding_model = None

load_dotenv()

class ESClient:
    def __init__(self):
        host = os.getenv("ELASTICSEARCH_HOST", "http://localhost:9200")
        self.product_index = os.getenv("INDEX_NAME", "products") # <-- Dùng biến
        self.log_index = "click_logs" # <-- Index mới
        try:
            self.client = Elasticsearch(
                hosts=[host], verify_certs=False, ssl_show_warn=False, request_timeout=30
            )
            if not self.client.ping(): raise ConnectionError("ES ping failed.")
            print(f"✅ Kết nối ES thành công tại {host}")
        except Exception as e: print(f"❌ Lỗi kết nối ES: {e}"); raise

    # === HÀM GHI LOG CLICK (MỚI) ===
    def log_click(self, product_id: str):
        """Ghi một sự kiện click (đồng bộ - sync)"""
        try:
            log_document = {
                "product_id": product_id, # Lưu _id của sản phẩm
                "timestamp": datetime.utcnow()
            }
            self.client.index(
                index=self.log_index,
                document=log_document,
                refresh="wait_for" # Đảm bảo ghi ngay
            )
            return True
        except Exception as e:
            print(f"❌ Lỗi log_click: {e}")
            return False

    # === HÀM LẤY SỐ LƯỢT CLICK (MỚI) ===
    def get_product_ratings(self, product_ids: list[str]) -> dict:
        """Lấy số lượt click cho 1 danh sách ID (đồng bộ - sync)"""
        if not product_ids:
            return {}
        try:
            query_body = {
                "size": 0,
                "query": {"terms": {"product_id": product_ids}},
                "aggs": {
                    "clicks_per_product": {
                        "terms": {"field": "product_id", "size": len(product_ids)}
                    }
                }
            }
            res = self.client.search(index=self.log_index, body=query_body)
            ratings_map = {}
            buckets = res.get('aggregations', {}).get('clicks_per_product', {}).get('buckets', [])
            for bucket in buckets:
                ratings_map[bucket['key']] = bucket['doc_count']
            
            # Gán 0 cho các ID không có trong buckets
            for pid in product_ids:
                if pid not in ratings_map:
                    ratings_map[pid] = 0
            return ratings_map
        except Exception as e:
            print(f"❌ Lỗi get_product_ratings: {e}")
            return {pid: 0 for pid in product_ids} # Trả về 0 nếu lỗi

    # === HÀM TIỆN ÍCH GHÉP SAO (MỚI) ===
    def _merge_ratings_to_hits(self, hits: list) -> list:
        """Nhận list 'hits', lấy ID, đếm click, và ghép 'rating_count' vào"""
        product_ids = [hit['_id'] for hit in hits]
        if not product_ids:
            return hits
        
        ratings_map = self.get_product_ratings(product_ids)
        
        for hit in hits:
            hit['rating_count'] = ratings_map.get(hit['_id'], 0)
        
        return hits

    # --- HÀM KEYWORD SEARCH (ĐÃ CẬP NHẬT) ---
    def keyword_search(self, index_name, query_text, category_filter=None, size=20):
        if not query_text: return []
        keywords = query_text.split()
        if not keywords: return []
        
        # (Giữ nguyên logic query của em)
        should_clauses = []
        for keyword in keywords:
            should_clauses.append({"match": {"name": {"query": keyword, "boost": 2}}})
            should_clauses.append({"match": {"description": keyword}})
        query_body = {"size": size, "query": {"bool": {"should": should_clauses, "minimum_should_match": 1, "filter": []}}}
        if category_filter: query_body["query"]["bool"]["filter"].append({"term": {"category": category_filter}})
        
        try:
            print(f"🔍 Tìm kiếm Keyword (Keywords: {keywords}, Category: {category_filter})...")
            res = self.client.search(index=index_name, body=query_body)
            hits = [{"_id": hit['_id'], **hit['_source']} for hit in res['hits']['hits']]
            
            # === THÊM BƯỚC GHÉP SAO ===
            hits_with_ratings = self._merge_ratings_to_hits(hits)
            # =========================
            
            print(f"✅ Tìm thấy {len(hits_with_ratings)} kết quả Keyword.")
            return hits_with_ratings
        except Exception as e: 
            print(f"❌ Lỗi Keyword Search: {e}"); return []

    # --- HÀM SEMANTIC SUGGESTIONS (ĐÃ CẬP NHẬT) ---
    async def semantic_search_suggestions(self, index_name, query_text, category_filter=None, k=5):
        if embedding_model is None: raise RuntimeError("Mô hình embedding chưa tải.")

        text_to_embed = query_text
        if category_filter:
            text_to_embed = f"{category_filter} | {query_text}"
        
        print(f"🧠 Đang tạo embedding (suggestions) cho: '{text_to_embed}'")
        loop = asyncio.get_event_loop()
        try:
            query_vector_np = await loop.run_in_executor(None, embedding_model.encode, text_to_embed)
            query_vector = query_vector_np.tolist()
        except Exception as e: raise RuntimeError(f"❌ Lỗi tạo embedding: {e}")

        knn_query = {"field": "product_embedding", "query_vector": query_vector, "k": k, "num_candidates": 50}

        try:
            res = self.client.search(index=index_name, knn=knn_query, size=k, _source=True)
            # Lấy _id và _source cho bước ghép sao
            hits = [{"_id": hit['_id'], "product": hit['_source'], "score": hit['_score']} for hit in res['hits']['hits']]
            
            # === THÊM BƯỚC GHÉP SAO ===
            # Trích xuất _id từ list 'hits' (mỗi 'hit' là 1 dict)
            product_ids = [hit['_id'] for hit in hits]
            ratings_map = self.get_product_ratings(product_ids)
            
            for hit in hits:
                # Gắn 'rating_count' vào 'product'
                hit['product']['rating_count'] = ratings_map.get(hit['_id'], 0)
            # =========================

            print(f"✅ Tìm thấy {len(hits)} gợi ý Semantic (combined text).")
            return hits
        except Exception as e:
            print(f"❌ Lỗi Semantic Suggestions (combined text): {e}")
            return []

    # --- HÀM SEARCH_PRODUCTS (ĐÃ CẬP NHẬT) ---
    def search_products(self, index_name, category_filter=None, page=1, size=20):
        try:
            start_from = (page - 1) * size
            query_body = {"from": start_from, "size": size, "query": {}}
            if category_filter: query_body["query"] = {"term": {"category": category_filter}}
            else: query_body["query"] = {"match_all": {}}
            
            print(f"🔍 Lấy sản phẩm (Category: {category_filter}, Page: {page}, Size: {size})...")
            res = self.client.search(index=index_name, body=query_body)
            hits = [{"_id": hit['_id'], **hit['_source']} for hit in res['hits']['hits']]
            total_hits = res['hits']['total']['value']
            
            # === THÊM BƯỚC GHÉP SAO ===
            hits_with_ratings = self._merge_ratings_to_hits(hits)
            # =========================

            print(f"✅ Lấy {len(hits_with_ratings)}/{total_hits} sản phẩm.")
            return {"data": hits_with_ratings, "total": total_hits}
        except Exception as e: 
            print(f"❌ Lỗi search_products: {e}"); return {"data": [], "total": 0}

    # --- HÀM GET_DOCUMENT (Giữ nguyên) ---
    def get_document(self, index_name, doc_id):
        try:
            res = self.client.get(index=index_name, id=doc_id)
            return {"_id": res['_id'], **res['_source']}
        except Exception as e: return None

    # --- HÀM KNN_SEARCH (ĐÃ CẬP NHẬT) ---
    def knn_search(self, index_name, query_vector, k=5, exclude_id=None):
        try:
            knn_query = {"field": "product_embedding", "query_vector": query_vector, "k": k + 1, "num_candidates": 50}
            query_filter = {"bool": {"must_not": [{"term": {"_id": exclude_id}}]}} if exclude_id else None
            
            res = self.client.search(index=index_name, knn=knn_query, query=query_filter, size=k, _source=True)
            
            # Lấy _id và _source cho bước ghép sao
            hits = [{"_id": hit['_id'], "product": hit['_source'], "score": hit['_score']} for hit in res['hits']['hits']]
            
            # === THÊM BƯỚC GHÉP SAO ===
            product_ids = [hit['_id'] for hit in hits]
            ratings_map = self.get_product_ratings(product_ids)
            for hit in hits:
                hit['product']['rating_count'] = ratings_map.get(hit['_id'], 0)
            # =========================
            
            return hits
        except Exception as e: 
            print(f"❌ Lỗi kNN: {e}"); return []

# --- Tạo instance (Giữ nguyên) ---
try:
    es_client = ESClient()
except ConnectionError as e: 
    print(f"❌ Không thể khởi tạo ESClient: {e}"); es_client = None
