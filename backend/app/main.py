# main.py
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from .es_client import es_client, embedding_model # Import đúng
from typing import List, Optional, Dict, Any # <-- Thêm Dict, Any
from pydantic import BaseModel # <-- Thêm Pydantic
import os

app = FastAPI(
    title="Product Recommendation API (Keyword + Semantic)",
    description="API tìm kiếm và gợi ý sản phẩm."
)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

INDEX_NAME = os.getenv("INDEX_NAME", "products")

# === Pydantic Model cho Click (MỚI) ===
class ClickLog(BaseModel):
    product_id: str

# === Startup Event (Giữ nguyên) ===
@app.on_event("startup")
async def startup_event():
    if es_client is None: raise RuntimeError("Không thể kết nối tới Elasticsearch.")
    if embedding_model is None: print("⚠️ CẢNH BÁO: Mô hình embedding chưa tải xong...")
    print("✅ FastAPI đã khởi động và kết nối ES thành công.")

@app.get("/")
def read_root(): return {"message": "Welcome to the Recommendation API!"}

# === ENDPOINT MỚI: Log Click ===
@app.post("/log-click", tags=["Logging"])
def log_click_endpoint(click_data: ClickLog):
    """
    Nhận sự kiện click từ frontend.
    Đây là hàm 'def' (sync) nên FastAPI sẽ tự chạy trong thread.
    """
    if es_client is None: raise HTTPException(status_code=503, detail="ES client lỗi.")
    
    success = es_client.log_click(click_data.product_id)
    
    if success:
        return {"status": "logged"}
    else:
        raise HTTPException(status_code=500, detail="Failed to log click")
# ===============================

# --- ENDPOINT KEYWORD SEARCH (Không đổi) ---
@app.get("/search-keyword", tags=["Search"])
async def keyword_search_endpoint(
    query: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    size: int = Query(20, ge=1, le=100),
    price_min: Optional[int] = Query(None),
    price_max: Optional[int] = Query(None)
):
    if es_client is None: raise HTTPException(status_code=503, detail="ES client lỗi.")
    try:
        # Nếu query trống, dùng wildcard "*" cho tìm kiếm toàn bộ
        search_query = query if query and query.strip() else "*"
        
        # Logic tính sao đã được chuyển vào bên trong hàm keyword_search
        price_range = None
        if price_min is not None and price_max is not None:
            price_range = (price_min, price_max)
        
        results = es_client.keyword_search(
            index_name=INDEX_NAME, query_text=search_query,
            category_filter=category, size=size, 
            apply_price_filter=True, manual_price_range=price_range
        )
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi keyword search: {e}")

# --- ENDPOINT SEMANTIC SUGGESTIONS (Không đổi) ---
@app.get("/search-semantic-suggestions", tags=["Search"])
async def semantic_suggestions_endpoint(
    query: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    price_min: Optional[int] = Query(None),
    price_max: Optional[int] = Query(None)
):
    if es_client is None: raise HTTPException(status_code=503, detail="ES client lỗi.")
    if embedding_model is None: raise HTTPException(status_code=503, detail="Mô hình embedding lỗi.")
    try:
        # Nếu query trống, không thể tính embedding, dùng wildcard "*" cho matching toàn bộ
        search_query = query if query and query.strip() else "*"
        
        # Logic tính sao đã được chuyển vào bên trong hàm này
        price_range = None
        if price_min is not None and price_max is not None:
            price_range = (price_min, price_max)
        
        results = await es_client.semantic_search_suggestions(
            index_name=INDEX_NAME, query_text=search_query,
            category_filter=category, k=5,
            apply_price_filter=True, manual_price_range=price_range
        )
        return results 
    except RuntimeError as e: raise HTTPException(status_code=500, detail=str(e))
    except Exception as e: raise HTTPException(status_code=500, detail=f"Lỗi semantic suggestions: {e}")

# --- ENDPOINT /products (Không đổi) ---
@app.get("/products", tags=["Products"])
async def get_products(
    category: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100)
):
    if es_client is None: raise HTTPException(status_code=503, detail="ES client lỗi.")
    try:
        # Logic tính sao đã được chuyển vào bên trong hàm search_products
        result_dict = es_client.search_products(
            index_name=INDEX_NAME,
            category_filter=category,
            page=page,
            size=size
        )
        # Giữ nguyên logic unpack của em
        return {"page": page, "size": size, **result_dict}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi tải sản phẩm: {e}")

# --- ENDPOINT /recommend (ĐÃ CẬP NHẬT) ---
@app.get("/recommend/{product_doc_id}", tags=["Products"])
async def get_recommendations(product_doc_id: str):
    """
    Lấy chi tiết 1 SP và 5 SP gợi ý (Tất cả đều đã được ghép 'rating_count')
    """ 
    if es_client is None: raise HTTPException(status_code=503, detail="ES client lỗi.")
    try:
        # 1. Lấy sản phẩm gốc
        original_doc = es_client.get_document(INDEX_NAME, product_doc_id)
        if not original_doc: 
            raise HTTPException(status_code=404, detail=f"Không tìm thấy ID: {product_doc_id}")
        
        # 2. Lấy vector
        product_source = {k: v for k, v in original_doc.items() if k != '_id'}
        query_vector = product_source.get("product_embedding")
        if not query_vector: 
            raise HTTPException(status_code=500, detail="Thiếu embedding vector")

        # 3. Lấy gợi ý (hàm knn_search đã tự động ghép sao)
        recommendations = es_client.knn_search(
            index_name=INDEX_NAME, query_vector=query_vector, k=5, exclude_id=product_doc_id
        )
        
        # 4. Ghép sao cho SẢN PHẨM GỐC
        rating_map = es_client.get_product_ratings([product_doc_id])
        product_source['rating_count'] = rating_map.get(product_doc_id, 0)

        return {"original_product": product_source, "recommendations": recommendations}
    except HTTPException as he: raise he
    except Exception as e: raise HTTPException(status_code=500, detail=f"Lỗi gợi ý: {e}")

# --- ENDPOINT /categories (Không đổi) ---
@app.get("/categories", tags=["Products"])
async def get_categories():
    if es_client is None: raise HTTPException(status_code=503, detail="ES client lỗi.")
    try:
        query = {"size": 0, "aggs": {"unique_categories": {"terms": {"field": "category", "size": 100}}}}
        res = es_client.client.search(index=INDEX_NAME, body=query, request_timeout=30)
        categories = [bucket["key"] for bucket in res["aggregations"]["unique_categories"]["buckets"]]
        categories.sort()
        return categories
    except Exception as e: 
        print(f"Lỗi lấy categories: {e}"); return []