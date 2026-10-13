import json
import sys
import os
from elasticsearch import Elasticsearch, helpers
from dotenv import load_dotenv

load_dotenv()

# --- Cấu hình ---
ES_HOST = os.getenv("ELASTICSEARCH_HOST", "http://localhost:9200")
PRODUCT_INDEX_NAME = os.getenv("INDEX_NAME", "products")
LOG_INDEX_NAME = "click_logs"  # <-- TÊN INDEX MỚI
INPUT_JSON = os.getenv("EMBEDDED_JSON_FILE", "data/mock_products_with_embedding.json")
try:
    VECTOR_DIM = int(os.getenv("VECTOR_DIM", 384))
except ValueError:
    print("❌ Lỗi: VECTOR_DIM trong .env phải là số nguyên.")
    sys.exit(1)
# ------------------

# === MAPPING CHO SẢN PHẨM ===
def get_es_product_mapping():
    return {
        "properties": {
            "id": {"type": "keyword"},
            "name": {"type": "text", "analyzer": "standard"},
            "description": {"type": "text", "analyzer": "standard"},
            "category": {"type": "keyword"},
            "price": {"type": "float"},
            "image_url": {"type": "keyword", "index": False},
            "data_hash": {"type": "keyword", "index": False},
            "product_embedding": {
                "type": "dense_vector", "dims": VECTOR_DIM,
                "index": "true", "similarity": "cosine",
                "index_options": {
                    "type": "hnsw",
                    "m": 16,
                    "ef_construction": 100
                }
            }
        }
    }

# === MAPPING CHO LOG CLICK (MỚI) ===
def get_es_log_mapping():
    return {
        "properties": {
            "product_id": {"type": "keyword"}, # Sẽ lưu _id của sản phẩm
            "timestamp": {"type": "date"}
        }
    }
# -----------------------------

def connect_es():
    try:
        es = Elasticsearch(
            hosts=[ES_HOST], 
            verify_certs=False, 
            ssl_show_warn=False,
            request_timeout=30 # Thêm request_timeout
        )
        if not es.ping(): raise ConnectionError("Ping tới Elasticsearch thất bại.")
        print(f"✅ Kết nối thành công tới Elasticsearch tại {ES_HOST}")
        return es
    except Exception as e:
        print(f"❌ Lỗi kết nối Elasticsearch: {e}")
        sys.exit(1)

def load_json_data(file_path, encoding='utf-8-sig'):
    # (Giữ nguyên code load_json_data của em)
    if not os.path.exists(file_path):
        print(f"❌ Lỗi: Không tìm thấy file dữ liệu '{file_path}'.")
        sys.exit(1)
    try:
        with open(file_path, 'r', encoding=encoding) as f:
            data = json.load(f)
            if not isinstance(data, list):
                print(f"❌ Lỗi: File JSON '{file_path}' không phải list.")
                sys.exit(1)
            return data
    except Exception as e:
        print(f"❌ Lỗi đọc file {file_path}: {e}")
        sys.exit(1)


def generate_bulk_actions(products, index_name):
    """ Dùng ID gốc ('id') làm _id của Elasticsearch """
    for product in products:
        doc_id = product.get('id')
        if not doc_id:
            print(f"⚠️ Cảnh báo: Bỏ qua sản phẩm thiếu 'id': {product.get('name')}")
            continue
            

        yield { 
            "_op_type": "index", 
            "_index": index_name,
            "_id": str(doc_id), # Dùng ID gốc làm ID tài liệu (phải là string)
            "_source": product 
        }
        # =====================


def main():
    print(f"\n--- Bắt đầu quy trình nạp dữ liệu vào Elasticsearch ---")
    es = connect_es()
    
    # === TẠO INDEX SẢN PHẨM ===
    product_mapping = get_es_product_mapping()
    try:
        if es.indices.exists(index=PRODUCT_INDEX_NAME):
            print(f"Index '{PRODUCT_INDEX_NAME}' đã tồn tại. (Bỏ qua việc xóa/tạo lại)")
            # Bỏ qua xóa để giữ lại click logs
            # print(f"⏳ Index '{PRODUCT_INDEX_NAME}' đã tồn tại. Đang xóa...")
            # es.indices.delete(index=PRODUCT_INDEX_NAME, ignore=[400, 404])
        # print(f"⏳ Đang tạo index '{PRODUCT_INDEX_NAME}' mới...")
        # es.indices.create(index=PRODUCT_INDEX_NAME, mappings=product_mapping)
        else:
            print(f"⏳ Đang tạo index '{PRODUCT_INDEX_NAME}'...")
            es.indices.create(index=PRODUCT_INDEX_NAME, mappings=product_mapping)
            print("✅ Tạo index sản phẩm thành công.")
    except Exception as e:
        print(f"❌ Lỗi khi thiết lập index '{PRODUCT_INDEX_NAME}': {e}")
        sys.exit(1)

    # === TẠO INDEX LOG CLICK (MỚI) ===
    log_mapping = get_es_log_mapping()
    try:
        if not es.indices.exists(index=LOG_INDEX_NAME):
            print(f"⏳ Đang tạo index '{LOG_INDEX_NAME}'...")
            es.indices.create(index=LOG_INDEX_NAME, mappings=log_mapping)
            print("✅ Tạo index log thành công.")
        else:
            print(f"Index '{LOG_INDEX_NAME}' đã tồn tại.")
    except Exception as e:
        print(f"❌ Lỗi khi thiết lập index '{LOG_INDEX_NAME}': {e}")
        # Không thoát, tiếp tục chạy
    # ---------------------------------

    products = load_json_data(INPUT_JSON)
    if not products:
        print("⚠️ Không có sản phẩm nào để nạp.")
        return

    print(f"⏳ Chuẩn bị nạp/cập nhật {len(products)} sản phẩm vào '{PRODUCT_INDEX_NAME}'...")
    actions = generate_bulk_actions(products, PRODUCT_INDEX_NAME)
    
    try:
        success_count, failed_items = helpers.bulk(es, actions, raise_on_error=False, raise_on_exception=False, request_timeout=60)
        fail_count = len(failed_items)

        print(f"\n--- ✅ HOÀN TẤT ---")
        print(f"📥 Nạp thành công: {success_count} sản phẩm.")
        if fail_count > 0:
            print(f"❌ Thất bại: {fail_count} sản phẩm.")
            # (Giữ nguyên code in lỗi của em)
    except Exception as e:
        print(f"❌ Lỗi nghiêm trọng khi thực hiện bulk import: {e}")

if __name__ == "__main__":
    main()

