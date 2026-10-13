import json
import os
import hashlib
from tqdm import tqdm
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()

# --- Cấu hình ---
RAW_FILE_PATH = os.getenv('PREPROCESSED_JSON_FILE', 'data/mock_products.json')
EMBED_FILE_PATH = os.getenv('EMBEDDED_JSON_FILE', 'data/mock_products_with_embedding.json')
MODEL_NAME = os.getenv('MODEL_NAME', 'bkai-foundation-models/vietnamese-bi-encoder')
# ------------------

def _create_product_hash(product):
    keys_to_hash = ['id', 'name', 'description', 'category', 'price', 'image_url']
    content_string = "".join(str(product.get(key, '')) for key in keys_to_hash)
    return hashlib.md5(content_string.encode('utf-8')).hexdigest()

def load_json_data(file_path, encoding='utf-8-sig'):
    if not os.path.exists(file_path): return []
    try:
        with open(file_path, 'r', encoding=encoding) as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(f"⚠️ Cảnh báo: File {file_path} lỗi JSON. Coi như rỗng.")
        return []
    except Exception as e:
        print(f"❌ Lỗi đọc file {file_path}: {e}")
        return []

def load_model(model_name, device='cpu'):
    print(f"⏳ Đang tải mô hình '{model_name}' về (chỉ 1 lần nếu chưa có)...")
    try:
        model = SentenceTransformer(model_name, device=device)
        print("✅ Tải mô hình thành công.")
        return model
    except Exception as e:
        print(f"❌ LỖI NGHIÊM TRỌNG: Không tải được mô hình '{model_name}': {e}")
        return None

def main():
    print("\n--- Bắt đầu quy trình tạo Embedding ---")

    raw_products = load_json_data(RAW_FILE_PATH)
    if not raw_products:
        print(f"❌ Lỗi: Không tìm thấy hoặc không đọc được file dữ liệu thô '{RAW_FILE_PATH}'. Dừng lại.")
        return

    cached_products = load_json_data(EMBED_FILE_PATH)
    cached_map = {p.get('id'): p for p in cached_products if p.get('id')}

    products_to_keep = []
    products_to_embed = []
    texts_to_embed = []
    stats = {"kept": 0, "updated": 0, "new": 0}
    processed_ids = set()

    print(f"🔍 So sánh {len(raw_products)} sản phẩm thô với {len(cached_map)} sản phẩm đã cache...")

    for product in tqdm(raw_products, desc="🔎 So sánh dữ liệu"):
        product_id = product.get('id')
        if not product_id:
            print(f"⚠️ Cảnh báo: Bỏ qua sản phẩm thiếu ID: {product.get('name', 'Không tên')}")
            continue
        if product_id in processed_ids:
            print(f"⚠️ Cảnh báo: Bỏ qua ID sản phẩm trùng lặp trong file thô: {product_id}")
            continue
        processed_ids.add(product_id)

        current_hash = _create_product_hash(product)
        cached_product = cached_map.get(product_id)

        if cached_product and cached_product.get('data_hash') == current_hash:
            products_to_keep.append(cached_product)
            stats["kept"] += 1
        else:
            product['data_hash'] = current_hash
            content = f"Tên: {product.get('name','')}. Mô tả: {product.get('description','')}. Danh mục: {product.get('category','')}"
            products_to_embed.append(product)
            texts_to_embed.append(content)
            stats["updated" if cached_product else "new"] += 1

    final_product_list = products_to_keep
    model = None

    if products_to_embed:
        print(f"\n⏳ Phát hiện {len(products_to_embed)} sản phẩm cần xử lý.")
        model = load_model(MODEL_NAME)
        if model is None:
            print("❌ Không thể tiếp tục vì không tải được model.")
            return

        print(f"🧠 Bắt đầu tạo embedding...")
        try:
            embeddings = model.encode(texts_to_embed, show_progress_bar=True, device='cpu')
            print("✅ Tạo embedding hoàn tất.")

            for i, product in enumerate(products_to_embed):
                product['product_embedding'] = embeddings[i].tolist()
                final_product_list.append(product)
        except Exception as e:
            print(f"❌ Lỗi nghiêm trọng khi tạo embedding: {e}")
            # return # Cân nhắc dừng nếu lỗi
    else:
        print("\n✅ Không có sản phẩm nào cần tạo embedding mới.")

    final_product_list.sort(key=lambda p: p.get('id', ''))

    try:
        os.makedirs(os.path.dirname(EMBED_FILE_PATH), exist_ok=True)
        with open(EMBED_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(final_product_list, f, indent=4, ensure_ascii=False)

        print(f"\n--- ✅ HOÀN TẤT ---")
        print(f"💾 Đã lưu {len(final_product_list)} sản phẩm vào '{EMBED_FILE_PATH}'")
        print(f"📊 Thống kê: Giữ nguyên: {stats['kept']} | Cập nhật: {stats['updated']} | Mới: {stats['new']}")

    except Exception as e:
        print(f"❌ Lỗi nghiêm trọng khi lưu file '{EMBED_FILE_PATH}': {e}")

if __name__ == "__main__":
    main()