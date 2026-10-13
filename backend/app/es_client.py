import os
from elasticsearch import Elasticsearch, helpers
from dotenv import load_dotenv
import asyncio
import json
from sentence_transformers import SentenceTransformer
import random
from datetime import datetime 
import sys

# --- Phần tải model  ---
try:
    EMBEDDING_MODEL_NAME = os.getenv('MODEL_NAME', 'bkai-foundation-models/vietnamese-bi-encoder') 
    embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME, device='cpu')
    print(f"✅ Tải mô hình embedding '{EMBEDDING_MODEL_NAME}' thành công.")
except Exception as e:
    print(f"❌ LỖI NGHIÊM TRỌNG: Không thể tải mô hình embedding: {e}")
    embedding_model = None

load_dotenv()

class ESClient:
    def __init__(self):
        host = os.getenv("ELASTICSEARCH_HOST", "http://localhost:9200")
        self.product_index = os.getenv("INDEX_NAME", "products") 
        self.log_index = "click_logs" 
        try:
            self.client = Elasticsearch(
                hosts=[host], verify_certs=False, ssl_show_warn=False, request_timeout=30
            )
            if not self.client.ping(): raise ConnectionError("ES ping failed.")
            print(f"✅ Kết nối ES thành công tại {host}")
        except Exception as e: print(f"❌ Lỗi kết nối ES: {e}"); raise

    # === HÀM GHI LOG CLICK   ===
    def log_click(self, product_id: str):
        """Ghi một sự kiện click (đồng bộ - sync)"""
        try:
            log_document = {
                "product_id": product_id, 
                "timestamp": datetime.utcnow()
            }
            self.client.index(
                index=self.log_index,
                document=log_document,
                refresh="wait_for" 
            )
            return True
        except Exception as e:
            print(f"❌ Lỗi log_click: {e}")
            return False

    # === HÀM LẤY SỐ LƯỢT CLICK   ===
    def get_product_ratings(self, product_ids: list[str]) -> dict:
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
            
            for pid in product_ids:
                if pid not in ratings_map:
                    ratings_map[pid] = 0
            return ratings_map
        except Exception as e:
            print(f"❌ Lỗi get_product_ratings: {e}")
            return {pid: 0 for pid in product_ids} 

    # === HÀM TIỆN ÍCH GHÉP SAO   ===
    def _merge_ratings_to_hits(self, hits: list) -> list:
        product_ids = [hit['_id'] for hit in hits]
        if not product_ids:
            return hits
        
        ratings_map = self.get_product_ratings(product_ids)
        
        for hit in hits:
            hit['rating_count'] = ratings_map.get(hit['_id'], 0)
        
        return hits

    # === HÀM TRÍCH XUẤT KHOẢNG GIÁ TỪ QUERY ===
    def extract_price_range_from_query(self, query_text):
        """
        Trích xuất khoảng giá từ query. Ví dụ:
        - \"laptop dưới 10 triệu\" -> (0, 10_000_000)
        - \"laptop 15-20 triệu\" -> (15_000_000, 20_000_000)
        - \"máy tính 10 triệu\" -> (9_000_000, 11_000_000)  # xung quanh 10 triệu
        - None nếu không tìm thấy giá
        """
        import re
        text = query_text.lower().strip()
        
        # Mẫu: \"X-Y triệu\" hoặc \"từ X đến Y triệu\"
        range_pattern = r'(\d+)\s*[-–]\s*(\d+)\s*triệu'
        match = re.search(range_pattern, text)
        if match:
            min_val = int(match.group(1)) * 1_000_000
            max_val = int(match.group(2)) * 1_000_000
            print(f"   ✓ Tìm thấy khoảng giá: {min_val:,} - {max_val:,}")
            return (min_val, max_val)
        
        # Mẫu: \"dưới X triệu\"
        under_pattern = r'(?:dưới|ít hơn)\s+(\d+)\s*triệu'
        match = re.search(under_pattern, text)
        if match:
            max_val = int(match.group(1)) * 1_000_000
            print(f"   ✓ Tìm thấy 'dưới' {max_val:,}")
            return (0, max_val)
        
        # Mẫu: \"trên X triệu\" hoặc \"hơn X triệu\"
        above_pattern = r'(?:trên|hơn|tối thiểu)\s+(\d+)\s*triệu'
        match = re.search(above_pattern, text)
        if match:
            min_val = int(match.group(1)) * 1_000_000
            print(f"   ✓ Tìm thấy 'trên' {min_val:,}")
            return (min_val, float('inf'))
        
        # Mẫu: \"khoảng X triệu\" hoặc chỉ \"X triệu\" (xung quanh giá đó)
        around_pattern = r'(?:khoảng|chừng)?\s*(\d+)\s*triệu'
        match = re.search(around_pattern, text)
        if match:
            center = int(match.group(1)) * 1_000_000
            # Xung quanh ±1 triệu
            print(f"   ✓ Tìm thấy xung quanh {center:,}")
            return (max(0, center - 1_000_000), center + 1_000_000)
        
        print(f"   ✗ Không tìm thấy giá trong: {query_text}")
        return None

    # === HÀM LỌC SẢN PHẨM THEO GIÁ ===
    def filter_by_price(self, products, price_range):
        """
        Lọc danh sách sản phẩm theo khoảng giá (min, max)
        """
        if not price_range:
            return products
        
        min_price, max_price = price_range
        filtered = []
        for product in products:
            price = product.get('price', 0)
            if min_price <= price <= max_price:
                filtered.append(product)
        
        print(f"   📊 Lọc giá: {len(products)} → {len(filtered)} sản phẩm (khoảng {min_price:,} - {max_price:,})")
        return filtered

    # --- HÀM KEYWORD SEARCH   ---
    def keyword_search(self, index_name, query_text, category_filter=None, size=20, apply_price_filter=True, manual_price_range=None):
        # Xử lý wildcard "*" - tìm kiếm toàn bộ (thường dùng khi chỉ filter giá)
        is_wildcard = query_text == "*"
        
        if not query_text or (not is_wildcard and not query_text.strip()): 
            return []
        
        keywords = [] if is_wildcard else query_text.split()
        
        # Trích xuất giá từ query hoặc sử dụng manual_price_range
        price_range = manual_price_range
        if not price_range and apply_price_filter:
            price_range = self.extract_price_range_from_query(query_text)
            if price_range:
                print(f"💰 Phát hiện khoảng giá từ query: {price_range[0]:,} - {price_range[1]:,} VND")
        elif price_range and apply_price_filter:
            print(f"💰 Sử dụng khoảng giá manual: {price_range[0]:,} - {price_range[1]:,} VND")
        
        # Xây dựng query body
        if is_wildcard:
            # Wildcard: match all, chỉ filter theo category và price
            query_body = {"size": size * 2, "query": {"bool": {"must": [{"match_all": {}}], "filter": []}}}
        else:
            # Keyword search
            should_clauses = []
            for keyword in keywords:
                should_clauses.append({"match": {"name": {"query": keyword, "boost": 2}}})
                should_clauses.append({"match": {"description": keyword}})
            query_body = {"size": size * 2, "query": {"bool": {"should": should_clauses, "minimum_should_match": 1, "filter": []}}}
        
        if category_filter: 
            query_body["query"]["bool"]["filter"].append({"term": {"category": category_filter}})

        try:
            print(f"🔍 Tìm kiếm Keyword (Keywords: {keywords if not is_wildcard else 'ALL'}, Category: {category_filter})...")
            res = self.client.search(index=index_name, body=query_body)
            hits = [{"_id": hit['_id'], **hit['_source']} for hit in res['hits']['hits']]
            
            # Lọc theo giá nếu có
            if price_range:
                hits = self.filter_by_price(hits, price_range)
            
            # Giới hạn kích thước cuối cùng
            hits = hits[:size]
            hits_with_ratings = self._merge_ratings_to_hits(hits)
            
            print(f"✅ Tìm thấy {len(hits_with_ratings)} kết quả Keyword (sau lọc giá).")
            return hits_with_ratings
        except Exception as e: 
            print(f"❌ Lỗi Keyword Search: {e}"); return []

    # --- HÀM SEMANTIC SUGGESTIONS   ---
    async def semantic_search_suggestions(self, index_name, query_text, category_filter=None, k=5, apply_price_filter=True, manual_price_range=None):
        # Không thể tạo embedding cho wildcard "*", nên skip semantic search
        if query_text == "*":
            print("⏭️ Bỏ qua semantic search cho wildcard query (không thể tạo embedding).")
            return []
        
        if embedding_model is None: raise RuntimeError("Mô hình embedding chưa tải.")

        text_to_embed = query_text
        if category_filter:
            text_to_embed = f"{category_filter} | {query_text}"
        
        # Trích xuất giá từ query hoặc sử dụng manual_price_range
        price_range = manual_price_range
        if not price_range and apply_price_filter:
            price_range = self.extract_price_range_from_query(query_text)
            if price_range:
                print(f"💰 Phát hiện khoảng giá từ query: {price_range[0]:,} - {price_range[1]:,} VND")
        elif price_range and apply_price_filter:
            print(f"💰 Sử dụng khoảng giá manual: {price_range[0]:,} - {price_range[1]:,} VND")
        
        print(f"🧠 Đang tạo embedding (suggestions) cho: '{text_to_embed}'")
        loop = asyncio.get_event_loop()
        try:
            query_vector_np = await loop.run_in_executor(None, embedding_model.encode, text_to_embed)
            query_vector = query_vector_np.tolist()
        except Exception as e: raise RuntimeError(f"❌ Lỗi tạo embedding: {e}")

        knn_query = {"field": "product_embedding", "query_vector": query_vector, "k": k * 3, "num_candidates": 100}

        try:
            res = self.client.search(index=index_name, knn=knn_query, size=k * 3, _source=True)
            hits = [{"_id": hit['_id'], "product": hit['_source'], "score": hit['_score']} for hit in res['hits']['hits']]
            
            # Lọc theo giá nếu có
            if price_range:
                products = [h['product'] for h in hits]
                filtered_products = self.filter_by_price(products, price_range)
                # Tạo lại danh sách hits với các sản phẩm đã lọc
                filtered_ids = {p.get('id'): True for p in filtered_products}
                hits = [h for h in hits if h['product'].get('id') in filtered_ids]
            
            # Giới hạn kích thước cuối cùng
            hits = hits[:k]
            
            product_ids = [hit['_id'] for hit in hits]
            ratings_map = self.get_product_ratings(product_ids)
            
            for hit in hits:
                hit['product']['rating_count'] = ratings_map.get(hit['_id'], 0)

            print(f"✅ Tìm thấy {len(hits)} gợi ý Semantic (sau lọc giá).")
            return hits
        except Exception as e:
            print(f"❌ Lỗi Semantic Suggestions (combined text): {e}")
            return []

    # --- HÀM SEARCH_PRODUCTS   ---
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
            
            hits_with_ratings = self._merge_ratings_to_hits(hits)

            print(f"✅ Lấy {len(hits_with_ratings)}/{total_hits} sản phẩm.")
            return {"data": hits_with_ratings, "total": total_hits}
        except Exception as e: 
            print(f"❌ Lỗi search_products: {e}"); return {"data": [], "total": 0}

    # --- HÀM GET_DOCUMENT   ---
    def get_document(self, index_name, doc_id):
        try:
            res = self.client.get(index=index_name, id=doc_id)
            return {"_id": res['_id'], **res['_source']}
        except Exception as e: return None

    # --- HÀM KNN_SEARCH  ---
    def knn_search(self, index_name, query_vector, k=5, exclude_id=None):
        try:
            # Request one extra candidate when we need to exclude the original id,
            # then filter it out in Python and return exactly `k` recommendations.
            requested_k = k + 1 if exclude_id else k
            knn_query = {
                "field": "product_embedding",
                "query_vector": query_vector,
                "k": requested_k,
                "num_candidates": 50
            }

            # Use an ES-level filter only as a best-effort; always defensively
            # remove the excluded id in Python to guarantee it does not appear.
            query_filter = None
            if exclude_id:
                query_filter = {
                    "bool": {
                        "must_not": [
                            {"ids": {"values": [str(exclude_id)]}}
                        ]
                    }
                }

            res = self.client.search(
                index=index_name,
                knn=knn_query,
                query=query_filter,
                size=requested_k,
                _source=True
            )

            hits = [{"_id": hit['_id'], "product": hit['_source'], "score": hit.get('_score')} for hit in res['hits']['hits']]

            # Defensively remove the original product if present and trim to k results
            if exclude_id:
                exclude_str = str(exclude_id)
                hits = [h for h in hits if h['_id'] != exclude_str]

            hits = hits[:k]

            product_ids = [hit['_id'] for hit in hits]
            ratings_map = self.get_product_ratings(product_ids)
            for hit in hits:
                hit['product']['rating_count'] = ratings_map.get(hit['_id'], 0)

            return hits
        except Exception as e: 
            print(f"❌ Lỗi kNN: {e}"); return []

# --- Tạo instance   ---
try:
    es_client = ESClient()
except ConnectionError as e: 
    print(f"❌ Không thể khởi tạo ESClient: {e}"); es_client = None



