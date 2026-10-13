import os
import sys
import json
from elasticsearch import Elasticsearch, NotFoundError
from dotenv import load_dotenv
from tqdm import tqdm
import numpy as np

# --- KHÔNG CẦN ml_metrics NỮA ---

load_dotenv()
ES_HOST = os.getenv("ELASTICSEARCH_HOST", "http://localhost:9200")
INDEX_NAME = os.getenv("INDEX_NAME", "products")
TOP_K = 5

def connect_es():
    """Kết nối tới Elasticsearch"""
    try:
        es = Elasticsearch(hosts=[ES_HOST], verify_certs=False, ssl_show_warn=False)
        if not es.ping(): raise ConnectionError("Ping tới Elasticsearch thất bại.")
        print(f"✅ Kết nối thành công tới Elasticsearch tại {ES_HOST}")
        return es
    except Exception as e:
        print(f"❌ Lỗi kết nối Elasticsearch: {e}")
        sys.exit(1)

def get_all_products_with_embedding(es, index_name):
    """Tải tất cả sản phẩm (chỉ các trường cần thiết) từ ES"""
    print(f"⏳ Đang tải tất cả sản phẩm và embedding từ index '{index_name}'...")
    all_hits = []
    try:
        # Dùng scroll để lấy dữ liệu lớn
        resp = es.search(
            index=index_name, query={"match_all": {}}, scroll='2m', size=100,
            _source_includes=["id", "name", "category", "product_embedding"]
        )
        scroll_id = resp['_scroll_id']
        all_hits.extend(resp['hits']['hits'])

        while len(resp['hits']['hits']):
            resp = es.scroll(scroll_id=scroll_id, scroll='2m')
            scroll_id = resp['_scroll_id']
            all_hits.extend(resp['hits']['hits'])

        print(f"✅ Đã tải {len(all_hits)} sản phẩm.")
        try: es.clear_scroll(scroll_id=scroll_id)
        except NotFoundError: pass

        products = [{"_id": hit['_id'], **hit['_source']} for hit in all_hits]
        return products
    except Exception as e:
        print(f"❌ Lỗi khi tải sản phẩm từ Elasticsearch: {e}")
        return []

def find_similar_for_eval(es, index_name, query_vector, exclude_doc_id, k):
    """Tìm k sản phẩm tương tự, trả về list {_id, category, score}"""
    try:
        knn_query = {"field": "product_embedding", "query_vector": query_vector, "k": k + 1, "num_candidates": 50}
        
        # Dùng 'ids' query để loại trừ chính xác sản phẩm đang query
        query_filter = {
            "bool": {
                "must_not": [
                    {"ids": {"values": [str(exclude_doc_id)]}}
                ]
            }
        }
        
        res = es.search(
            index=index_name, knn=knn_query, query=query_filter, size=k,
            _source_includes=["category"] # Chỉ cần category
        )
        return [{"_id": hit['_id'], "category": hit['_source'].get('category'), "score": hit['_score']}
                for hit in res['hits']['hits']]
    except Exception as e:
        return []

def calculate_basic_metrics(query_product, recommendations, k):
    """
    Tính toán 2 chỉ số cơ bản: Avg Cosine và Precision@K.
    Ground truth: Cùng 'category' là 'relevant'.
    """
    if not recommendations:
        return {"avg_cosine": 0.0, "precision_at_k": 0.0}

    query_category = query_product.get('category')
    num_correct = 0
    total_cosine_sim = 0.0

    for reco in recommendations:
        es_score = reco['score']
        # Đổi điểm của ES (0->1) về Cosine Similarity (-1 -> 1)
        cosine_sim = max(0.0, (es_score * 2) - 1)
        total_cosine_sim += cosine_sim

        if reco['category'] == query_category:
            num_correct += 1

    avg_cosine = total_cosine_sim / len(recommendations) if recommendations else 0.0
    precision_at_k = num_correct / k

    return {
        "avg_cosine": avg_cosine,
        "precision_at_k": precision_at_k
    }

def calculate_ap_at_k(actual_relevant_set, predicted_reco_ids, k):
    """
    Tự tính Average Precision at K (AP@K) thủ công.
    Không cần thư viện ml_metrics.
    """
    if not actual_relevant_set:
        return 0.0 # Không có gì đúng để so sánh
    
    if not predicted_reco_ids:
        return 0.0 # Không có gì để gợi ý

    ap = 0.0
    relevant_hits = 0
    
    # Duyệt qua từng gợi ý để tính điểm xếp hạng
    for i, reco_id in enumerate(predicted_reco_ids[:k]):
        # i bắt đầu từ 0, (i + 1) là vị trí (rank)
        if reco_id in actual_relevant_set:
            relevant_hits += 1
            precision_at_i = relevant_hits / (i + 1)
            ap += precision_at_i

    if relevant_hits == 0:
        return 0.0
    
    # Chia cho tổng số ground truth khả thi (min của K hoặc tổng số đúng)
    return ap / min(len(actual_relevant_set), k)

def preprocess_products(all_products):
    """
    Tạo map category -> set các _id để tìm ground truth nhanh.
    Giúp tính mAP nhanh hơn thay vì loop lồng nhau.
    """
    products_by_category = {}
    for p in all_products:
        category = p.get('category')
        _id = p.get('_id')
        if category and _id:
            if category not in products_by_category:
                products_by_category[category] = set()
            products_by_category[category].add(_id)
    return products_by_category

def main():
    print("\n--- Bắt đầu quy trình đánh giá hệ thống gợi ý (No Libraries) ---")
    es = connect_es()
    all_products = get_all_products_with_embedding(es, INDEX_NAME)

    if not all_products:
        print("❌ Không có sản phẩm nào để đánh giá.")
        return

    # Xử lý trước để tìm ground truth nhanh hơn
    print("⏳ Xử lý trước dữ liệu ground truth (category)...")
    products_by_category = preprocess_products(all_products)

    total_avg_cosine = 0.0
    total_precision_at_k = 0.0
    total_map_at_k = 0.0 # Biến tích lũy mAP
    evaluated_count = 0

    print(f"\n⚙️ Đánh giá Top-{TOP_K} gợi ý cho {len(all_products)} sản phẩm...")
    
    # Vòng lặp chính (đã sửa lỗi thụt đầu dòng)
    for product in tqdm(all_products, desc="📊 Đang đánh giá"):
        product_doc_id = product.get('_id')
        query_vector = product.get('product_embedding')
        query_category = product.get('category')

        if not product_doc_id or not query_vector or not query_category:
            continue
        
        # 1. Tìm K gợi ý từ ES
        recommendations = find_similar_for_eval(es, INDEX_NAME, query_vector, product_doc_id, TOP_K)
        
        # 2. Tính điểm cơ bản (Cosine, Precision)
        metrics = calculate_basic_metrics(product, recommendations, TOP_K)

        # 3. Tính AP@K thủ công (cho mAP)
        # Lấy ground truth: là TẤT CẢ sản phẩm cùng category (trừ chính nó)
        actual_relevant_set = products_by_category.get(query_category, set()).copy()
        if product_doc_id in actual_relevant_set:
            actual_relevant_set.remove(product_doc_id)
        
        # Lấy danh sách ID đã được gợi ý
        predicted_reco_ids = [reco['_id'] for reco in recommendations]
        
        # Gọi hàm tự viết
        ap_at_k = calculate_ap_at_k(actual_relevant_set, predicted_reco_ids, TOP_K)
        
        # 4. Cộng dồn tổng điểm
        total_avg_cosine += metrics['avg_cosine']
        total_precision_at_k += metrics['precision_at_k']
        total_map_at_k += ap_at_k
        evaluated_count += 1

    if evaluated_count == 0:
        print("❌ Không có sản phẩm hợp lệ nào được đánh giá.")
        return

    # Tính trung bình cộng
    mean_avg_cosine = total_avg_cosine / evaluated_count
    mean_precision_at_k = total_precision_at_k / evaluated_count
    mean_ap_at_k = total_map_at_k / evaluated_count 

    print("\n" + "="*50)
    print(f"--- 📈 KẾT QUẢ ĐÁNH GIÁ (K={TOP_K}) ---")
    print("="*50)
    print(f"  - Số sản phẩm đánh giá hợp lệ: {evaluated_count}")
    print(f"  - Average Cosine Similarity trung bình: {mean_avg_cosine:.4f}")
    print(f"  - Mean Precision@{TOP_K} (P@{TOP_K}):      {mean_precision_at_k:.4f}")
    print(f"  - Mean Average Precision@{TOP_K} (mAP@{TOP_K}): {mean_ap_at_k:.4f}")
    print("-"*50)
    print("ℹ️ Ground Truth: Cùng Category.")
    print("="*50)

if __name__ == "__main__":
    main()