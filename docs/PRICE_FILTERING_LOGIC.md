# Logic Xử Lý Giá (Price Filtering Logic)

## 1. Tổng Quan

Hệ thống có khả năng **tự động nhận diện** giá từ text tìm kiếm của user. Khi user gõ "laptop dưới 5 triệu" hoặc "điện thoại 10-15 triệu", hệ thống sẽ:

1. Phân tích text tìm kiếm
2. Trích xuất thông tin giá từ text
3. Chuyển đổi text giá thành phạm vi số (min, max)
4. Lọc sản phẩm theo giá số

---

## 2. Các Mẫu Giá Được Hỗ Trợ

| Mẫu Text | Giá Min | Giá Max | Ví Dụ |
|---------|---------|---------|-------|
| "dưới X triệu" | 0 | X triệu | "dưới 5 triệu" → 0 - 5,000,000 |
| "X-Y triệu" | X triệu | Y triệu | "5-10 triệu" → 5,000,000 - 10,000,000 |
| "X triệu trở lên" | X triệu | ∞ | "10 triệu trở lên" → 10,000,000 - ∞ |
| "trên X triệu" | X triệu | ∞ | "trên 10 triệu" → 10,000,000 - ∞ |
| "từ X triệu" | X triệu | ∞ | "từ 15 triệu" → 15,000,000 - ∞ |

---

## 3. Vị Trí Code Xử Lý Giá

### 3.1 Backend - Hàm Trích Xuất Giá

**File**: `backend/app/es_client.py`

**Hàm**: `extract_price_range_from_query()`

```python
def extract_price_range_from_query(self, query_text):
    """
    Trích xuất phạm vi giá từ text tìm kiếm.
    
    Ví dụ đầu vào:
    - "laptop dưới 5 triệu"
    - "điện thoại 5-10 triệu"
    - "máy tính bảng trên 10 triệu"
    
    Trả về: (min_price, max_price) hoặc None nếu không tìm thấy
    """
    
    # Pattern 1: "X-Y triệu" (range như "5-10 triệu")
    range_match = re.search(r'(\d+(?:[.,]\d+)?)\s*-\s*(\d+(?:[.,]\d+)?)\s*triệu', query_text)
    if range_match:
        min_val = float(range_match.group(1).replace(',', '.'))
        max_val = float(range_match.group(2).replace(',', '.'))
        return (int(min_val * 1_000_000), int(max_val * 1_000_000))
    
    # Pattern 2: "dưới X triệu" (under X million)
    under_match = re.search(r'dưới\s+(\d+(?:[.,]\d+)?)\s*triệu', query_text)
    if under_match:
        max_val = float(under_match.group(1).replace(',', '.'))
        return (0, int(max_val * 1_000_000))
    
    # Pattern 3: "trên X triệu", "X triệu trở lên", "từ X triệu" (above X million)
    above_match = re.search(r'(?:trên|từ)\s+(\d+(?:[.,]\d+)?)\s*triệu|(\d+(?:[.,]\d+)?)\s*triệu\s+trở\s+lên', query_text)
    if above_match:
        min_val = float((above_match.group(1) or above_match.group(2)).replace(',', '.'))
        return (int(min_val * 1_000_000), float('inf'))  # Infinity = không giới hạn trên
    
    return None
```

---

## 4. Luồng Xử Lý Chi Tiết

### 4.1 Flow Từ User Gõ Tìm Kiếm → Backend

```
┌─────────────────────────────────────────────────────────────┐
│ 1. USER GỎ TEXT TÌMKIẾM                                      │
│    (Ví dụ: "laptop dưới 5 triệu")                            │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. FRONTEND GỬI HTTP REQUEST                                 │
│    GET /search-keyword?query=laptop%20dưới%205%20triệu      │
│    GET /search-semantic-suggestions?query=laptop%20...     │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. BACKEND NHẬN REQUEST (main.py)                           │
│    keyword_search_endpoint()                                │
│    semantic_suggestions_endpoint()                          │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. GỌI es_client FUNCTIONS (es_client.py)                  │
│    - keyword_search()                                       │
│    - semantic_search_suggestions()                          │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. TRÍCH XUẤT GIÁ TỪ QUERY                                  │
│    extract_price_range_from_query("laptop dưới 5 triệu")   │
│    ↓                                                        │
│    Tìm match: "dưới 5 triệu"                               │
│    ↓                                                        │
│    Trả về: (0, 5_000_000)                                  │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. TÌM KIẾM ELASTICSEARCH                                   │
│    - Tìm "laptop" trong name, description                   │
│    - Áp dụng filter: price >= 0 AND price <= 5_000_000     │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 7. TRẢN KẾT QUẢ                                             │
│    - Chỉ trả về products có:                                │
│      • Name/description chứa "laptop"                       │
│      • Price trong phạm vi 0-5,000,000                      │
└─────────────────────────────────────────────────────────────┘
```

---

## 5. Chi Tiết Regex Pattern

### 5.1 Phân Tích Regex Patterns

#### **Pattern 1: Range - "X-Y triệu"**

```python
r'(\d+(?:[.,]\d+)?)\s*-\s*(\d+(?:[.,]\d+)?)\s*triệu'
```

**Giải thích:**
- `(\d+(?:[.,]\d+)?)` - Số đầu (có thể có dấu phẩy/chấm)
  - `\d+` - Một hoặc nhiều chữ số
  - `(?:[.,]\d+)?` - Tùy chọn: dấu phẩy/chấm + chữ số (cho số lẻ)
- `\s*-\s*` - Dấu gạch ngang (với khoảng trắng xung quanh)
- `(\d+(?:[.,]\d+)?)` - Số thứ hai
- `\s*triệu` - Từ "triệu"

**Ví dụ Match:**
- "5-10 triệu" → Nhóm 1: "5", Nhóm 2: "10"
- "5-10triệu" → Vẫn match
- "5.5-10.5 triệu" → Nhóm 1: "5.5", Nhóm 2: "10.5"

**Chuyển Đổi:**
```python
min_val = 5 → 5_000_000
max_val = 10 → 10_000_000
```

---

#### **Pattern 2: Under - "dưới X triệu"**

```python
r'dưới\s+(\d+(?:[.,]\d+)?)\s*triệu'
```

**Giải thích:**
- `dưới` - Từ khóa "dưới"
- `\s+` - Một hoặc nhiều khoảng trắng
- `(\d+(?:[.,]\d+)?)` - Số
- `\s*triệu` - Từ "triệu" (khoảng trắng tùy chọn)

**Ví dụ Match:**
- "dưới 5 triệu" → Nhóm 1: "5"
- "dưới5triệu" → Không match (cần ít nhất 1 space sau "dưới")
- "dưới 5.5 triệu" → Nhóm 1: "5.5"

**Chuyển Đổi:**
```python
min = 0
max = 5 → 5_000_000
```

---

#### **Pattern 3: Above - "trên X triệu" / "X triệu trở lên" / "từ X triệu"**

```python
r'(?:trên|từ)\s+(\d+(?:[.,]\d+)?)\s*triệu|(\d+(?:[.,]\d+)?)\s*triệu\s+trở\s+lên'
```

**Giải thích:**
- `(?:trên|từ)` - "trên" hoặc "từ" (non-capturing group)
- Hoặc `|` - Hoặc
- `(\d+(?:[.,]\d+)?)\s*triệu\s+trở\s+lên` - "X triệu trở lên"

**Ví dụ Match:**
- "trên 10 triệu" → Nhóm 1: "10"
- "từ 15 triệu" → Nhóm 1: "15"
- "20 triệu trở lên" → Nhóm 2: "20"

**Chuyển Đổi:**
```python
min = 10 → 10_000_000
max = infinity (không giới hạn)
```

---

## 6. Xử Lý Số Lẻ và Định Dạng

### 6.1 Hàm Chuẩn Hóa

```python
# Chuyển "5,5" hoặc "5.5" thành 5.5
value_str = "5.5".replace(',', '.')  # Hoặc "5,5" → "5.5"
value_float = float(value_str)  # 5.5
value_vnd = int(value_float * 1_000_000)  # 5_500_000
```

**Ví dụ:**
- Input: "5,5 triệu" → Output: 5_500_000 VND
- Input: "5.5 triệu" → Output: 5_500_000 VND
- Input: "5 triệu" → Output: 5_000_000 VND

---

## 7. Lọc Elasticsearch

### 7.1 Hàm Lọc Giá

**File**: `backend/app/es_client.py`

**Hàm**: `filter_by_price()`

```python
def filter_by_price(self, products, price_range):
    """
    Lọc danh sách sản phẩm theo phạm vi giá.
    
    Args:
        products: Danh sách sản phẩm
        price_range: (min_price, max_price) tuple
    
    Returns:
        Danh sách sản phẩm trong phạm vi giá
    """
    min_price, max_price = price_range
    
    filtered = []
    for product in products:
        price = product.get('price', 0)
        
        # Kiểm tra điều kiện
        if price >= min_price:
            # Nếu max_price là infinity, không kiểm tra upper bound
            if max_price == float('inf') or price <= max_price:
                filtered.append(product)
    
    return filtered
```

**Logic:**
```
Nếu price_range = (0, 5_000_000)
  ✓ Product với price=3_000_000 → 3M >= 0 AND 3M <= 5M → PASS
  ✗ Product với price=6_000_000 → 6M >= 0 AND 6M > 5M → FAIL
  ✓ Product với price=5_000_000 → 5M >= 0 AND 5M <= 5M → PASS

Nếu price_range = (10_000_000, infinity)
  ✗ Product với price=9_000_000 → 9M < 10M → FAIL
  ✓ Product với price=10_000_000 → 10M >= 10M AND (infinity) → PASS
  ✓ Product với price=100_000_000 → 100M >= 10M AND (infinity) → PASS
```

---

## 8. Flow Code Chi Tiết (Keyword Search)

### 8.1 Hàm `keyword_search()` trong es_client.py

```python
def keyword_search(self, index_name, query_text, category_filter=None, 
                   size=20, apply_price_filter=True, manual_price_range=None):
    """
    Tìm kiếm sản phẩm theo keyword với tùy chọn lọc giá.
    """
    
    # ============= BƯỚC 1: Xử lý query =============
    is_wildcard = query_text == "*"  # Nếu là wildcard (tìm tất cả)
    
    if not query_text or (not is_wildcard and not query_text.strip()): 
        return []
    
    keywords = [] if is_wildcard else query_text.split()  # Tách từ khóa
    
    # ============= BƯỚC 2: Trích xuất giá =============
    price_range = manual_price_range  # Nếu có parameter giá manual
    
    if not price_range and apply_price_filter:
        # Trích xuất giá từ query text
        price_range = self.extract_price_range_from_query(query_text)
        if price_range:
            print(f"💰 Phát hiện khoảng giá từ query: {price_range[0]:,} - {price_range[1]:,} VND")
    elif price_range and apply_price_filter:
        print(f"💰 Sử dụng khoảng giá manual: {price_range[0]:,} - {price_range[1]:,} VND")
    
    # ============= BƯỚC 3: Xây dựng Elasticsearch query =============
    if is_wildcard:
        # Match tất cả products
        query_body = {
            "size": size * 2, 
            "query": {
                "bool": {
                    "must": [{"match_all": {}}], 
                    "filter": []
                }
            }
        }
    else:
        # Match các keyword
        should_clauses = []
        for keyword in keywords:
            should_clauses.append({
                "match": {"name": {"query": keyword, "boost": 2}}  # Name có trọng số cao hơn
            })
            should_clauses.append({
                "match": {"description": keyword}
            })
        
        query_body = {
            "size": size * 2, 
            "query": {
                "bool": {
                    "should": should_clauses, 
                    "minimum_should_match": 1,  # Ít nhất 1 keyword phải match
                    "filter": []
                }
            }
        }
    
    # Thêm category filter nếu có
    if category_filter: 
        query_body["query"]["bool"]["filter"].append({
            "term": {"category": category_filter}
        })
    
    # ============= BƯỚC 4: Thực hiện tìm kiếm ES =============
    print(f"🔍 Tìm kiếm Keyword (Keywords: {keywords if not is_wildcard else 'ALL'}, Category: {category_filter})...")
    
    res = self.client.search(index=index_name, body=query_body)
    hits = [{"_id": hit['_id'], **hit['_source']} for hit in res['hits']['hits']]
    
    # ============= BƯỚC 5: Lọc theo giá =============
    if price_range:
        original_count = len(hits)
        hits = self.filter_by_price(hits, price_range)
        filtered_count = len(hits)
        print(f"   📊 Lọc giá: {original_count} → {filtered_count} sản phẩm (khoảng {price_range[0]:,} - {price_range[1]:,})")
    
    # ============= BƯỚC 6: Giới hạn kích thước và merge ratings =============
    hits = hits[:size]  # Giới hạn kết quả
    hits_with_ratings = self._merge_ratings_to_hits(hits)
    
    print(f"✅ Tìm thấy {len(hits_with_ratings)} kết quả Keyword (sau lọc giá).")
    
    return hits_with_ratings
```

---

## 9. Ví Dụ Cụ Thể: "laptop dưới 5 triệu"

### 9.1 Luồng Thực Thi

**Bước 1**: User gõ "laptop dưới 5 triệu" và nhấn Enter

**Bước 2**: Frontend gửi request:
```
GET /search-keyword?query=laptop%20d%C6%B0%E1%BB%9Bi%205%20tri%E1%BB%87u
GET /search-semantic-suggestions?query=laptop%20d%C6%B0%E1%BB%9Bi%205%20tri%E1%BB%87u
```

**Bước 3**: Backend nhận query text: `"laptop dưới 5 triệu"`

**Bước 4**: Gọi `extract_price_range_from_query("laptop dưới 5 triệu")`
```python
# Regex match: r'dưới\s+(\d+(?:[.,]\d+)?)\s*triệu'
# Match found: "dưới 5 triệu"
# Group 1: "5"

min_val = float("5".replace(',', '.')) = 5.0
max_val = 5.0
return (5_000_000, 5_000_000)
```

**Bước 5**: Tách keyword từ query:
```python
keywords = "laptop dưới 5 triệu".split()
# = ["laptop", "dưới", "5", "triệu"]
```

**Bước 6**: Xây dựng Elasticsearch query:
```json
{
  "size": 40,
  "query": {
    "bool": {
      "should": [
        {"match": {"name": {"query": "laptop", "boost": 2}}},
        {"match": {"description": "laptop"}},
        {"match": {"name": {"query": "dưới", "boost": 2}}},
        {"match": {"description": "dưới"}},
        ...
      ],
      "minimum_should_match": 1,
      "filter": []
    }
  }
}
```

**Bước 7**: Elasticsearch trả về tất cả products có chứa các keyword

**Bước 8**: Python lọc theo giá:
```python
# price_range = (5_000_000, 5_000_000)
# Chỉ giữ products với price >= 5_000_000 AND price <= 5_000_000
# (chỉ cách gần đúng)
```

**Bước 9**: Trả về tối đa 20 results

---

## 10. Ví Dụ 2: "điện thoại 10-15 triệu"

### 10.1 Luồng Thực Thi

**Query text**: `"điện thoại 10-15 triệu"`

**Bước 1**: Extract price:
```python
# Regex match: r'(\d+(?:[.,]\d+)?)\s*-\s*(\d+(?:[.,]\d+)?)\s*triệu'
# Match: "10-15 triệu"
# Group 1: "10", Group 2: "15"

min_val = 10 → 10_000_000
max_val = 15 → 15_000_000
return (10_000_000, 15_000_000)
```

**Bước 2**: Keywords: `["điện", "thoại", "10-15", "triệu"]`

**Bước 3**: Elasticsearch tìm products chứa "điện" hoặc "thoại"

**Bước 4**: Filter lọc: giữ products với `10M <= price <= 15M`

**Result**: Điện thoại trong khoảng 10-15 triệu

---

## 11. Ví Dụ 3: "máy tính trên 20 triệu"

### 11.1 Luồng Thực Thi

**Query text**: `"máy tính trên 20 triệu"`

**Bước 1**: Extract price:
```python
# Regex match: r'(?:trên|từ)\s+(\d+(?:[.,]\d+)?)\s*triệu'
# Match: "trên 20 triệu"
# Group 1: "20"

min_val = 20 → 20_000_000
max_val = infinity (không giới hạn)
return (20_000_000, float('inf'))
```

**Bước 2**: Keywords: `["máy", "tính", "trên", "20", "triệu"]`

**Bước 3**: Elasticsearch tìm products chứa "máy" hoặc "tính"

**Bước 4**: Filter lọc: giữ products với `price >= 20M` (không có upper limit)

**Result**: Máy tính từ 20 triệu trở lên (không có giới hạn trên)

---

## 12. Backend Files Structure

```
backend/app/
├── main.py
│   └── @app.get("/search-keyword")
│       ├── Nhận query parameter
│       ├── Gọi es_client.keyword_search()
│       └── Trả về JSON results
│
└── es_client.py
    ├── extract_price_range_from_query()  ← HÀM CHÍNH TRÍCH XUẤT GIÁ
    ├── keyword_search()
    ├── semantic_search_suggestions()
    ├── filter_by_price()
    └── class ESClient()
```

---

## 13. Frontend Integration

### 13.1 Hàm Frontend Gửi Request

**File**: `frontend/app.js`

```javascript
async function fetchKeywordSearch(queryText, category, priceMin = null, priceMax = null) {
    const params = new URLSearchParams();
    if (queryText) params.append('query', queryText);
    if (category) params.append('category', category);
    if (priceMin !== null) params.append('price_min', priceMin);
    if (priceMax !== null) params.append('price_max', priceMax);
    
    const url = `http://localhost:8000/search-keyword?${params.toString()}`;
    
    const response = await fetch(url);
    const data = await response.json();
    
    // Hiển thị kết quả
    displayProducts(data, keywordResultsGrid);
}
```

**Flow**:
1. User nhập: "laptop dưới 5 triệu"
2. Gọi: `fetchKeywordSearch("laptop dưới 5 triệu", "")`
3. URL: `http://localhost:8000/search-keyword?query=laptop%20dưới%205%20triệu`
4. Backend nhận query, extract giá → filter → trả về results
5. Frontend hiển thị

---

## 14. Tóm Tắt Logic

```
┌─────────────────────────────────────────────────┐
│ USER INPUT: "laptop dưới 5 triệu"              │
└────────────┬────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────┐
│ REGEX MATCHING                                  │
│ Pattern: r'dưới\s+(\d+)\s*triệu'              │
│ Match: "dưới 5 triệu"                         │
│ Extract: number = 5                            │
└────────────┬────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────┐
│ NUMBER CONVERSION                               │
│ 5 * 1_000_000 = 5_000_000 VND                  │
│ price_range = (0, 5_000_000)                   │
└────────────┬────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────┐
│ ELASTICSEARCH SEARCH                            │
│ Find: products containing "laptop"             │
│ Filter: price >= 0 AND price <= 5_000_000      │
└────────────┬────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────┐
│ RETURN RESULTS                                  │
│ ✓ Laptop 3 triệu                               │
│ ✓ Laptop 4.5 triệu                             │
│ ✗ Laptop 7 triệu (ngoài range)                 │
└─────────────────────────────────────────────────┘
```

---

## 15. Các Trường Hợp Edge Case

### 15.1 Xử Lý Lỗi

| Input | Xử Lý |
|-------|--------|
| "laptop" | Không tìm giá → giá = None → tìm tất cả laptop |
| "100 triệu" | Không match regex → giá = None |
| "5-5 triệu" | Min = 5, Max = 5 → price chính xác = 5M |
| "0.5-2 triệu" | Min = 500K, Max = 2M → OK |
| "trên 0 triệu" | Min = 0, Max = ∞ → tất cả products |

### 15.2 Khi Nào Giá = None

```python
# Nếu không match regex, trả về None
# Backend vẫn tìm kiếm nhưng không lọc giá
# Ví dụ: "laptop không có keyword giá"
# → Tìm tất cả laptop, hiển thị hết
```

---

## 16. Kết Luận

Hệ thống sử dụng **Regex Patterns** để:

1. **Nhận diện giá**: Tìm text matching như "dưới X", "X-Y", "trên X"
2. **Trích xuất số**: Lấy giá trị X, Y từ text
3. **Chuyển đổi**: X triệu → X × 1,000,000 VND
4. **Lọc**: Chỉ giữ products trong phạm vi giá

**Ưu điểm:**
- ✅ Tự động nhận diện giá từ user input
- ✅ Không cần button riêng
- ✅ Hỗ trợ nhiều format
- ✅ Kết hợp với keyword search

**Hạn chế:**
- ⚠️ Phải gõ chính xác format
- ⚠️ Số lẻ cần dùng dấu phẩy/chấm
- ⚠️ Chỉ hỗ trợ VND, không hỗ trợ USD/currencies khác
