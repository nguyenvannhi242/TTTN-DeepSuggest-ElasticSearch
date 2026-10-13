# 📋 NHẬT KÝ DỰ ÁN & QUY TRÌNH HỆ THỐNG (LOG.MD)

> **Dự án:** Hệ thống Gợi ý Sản phẩm Thông minh (DeepSuggest Elasticsearch)  
> **Kiến trúc:** FastAPI + Elasticsearch 8.x (HNSW Vector Search) + Sentence Transformers (Bi-Encoder) + Vanilla Frontend  
> **Ngày cập nhật:** 14/10/2026  

---

## 📌 1. Xác Nhận & Tổng Hợp Quy Trình Hoạt Động Của Hệ Thống

Quy trình bạn đã nắm bắt là **hoàn toàn chính xác về mặt tổng thể**, và dưới đây là **chi tiết đầy đủ cùng các mắt xích kỹ thuật quan trọng bổ sung** để bức tranh quy trình được liền mạch và chuẩn xác nhất:

```
[1. Cào dữ liệu (Web Scraping)]
       │
       ▼ (Các file .xlsx theo danh mục: phone, laptop, vga, chuot, maygiat,...)
[2. Tiền xử lý & Gom nhóm tại Notebook] ──► preprocess_for_all.ipynb
       │
       ▼ (Output: raw_products.xlsx)
[3. Chuẩn hóa Data Pipeline] ──────────────► scripts/preprocess_csv.py
       │
       ▼ (Output: raw_products_utf8.csv & mock_products.json)
[4. Trích xuất Vector Embedding] ──────────► scripts/embed_to_json.py (Bi-Encoder + MD5 Cache)
       │
       ▼ (Output: mock_products_with_embedding.json)
[5. Khởi tạo & Đổ dữ liệu vào ES] ────────► scripts/import_to_elasticsearch.py (Indices: products & click_logs)
       │
       ├──► Orchestrator tự động hóa: run_all.py (Docker + Polling + Pipeline)
       │
[6. Backend Service (FastAPI)] ───────────► backend/app/main.py & es_client.py
       │                                     - Semantic kNN & Keyword Search
       │                                     - NLP Price Extraction ("dưới 5 triệu", "5-10 triệu")
       │                                     - Content-Based Recommendation (/recommend/{id})
       │                                     - Click Tracking & Rating Score (/log-click)
       ▼
[7. Giao diện Người dùng (Frontend)] ─────► frontend/ (HTML / CSS / JavaScript)
```

---

## 🔄 2. Chi Tiết Từng Bước Trong Quy Trình

### 🔹 Bước 1: Thu thập dữ liệu (Web Scraping / Crawling)
- **Nguồn:** Cào dữ liệu sản phẩm điện tử, công nghệ và gia dụng từ các trang TMĐT lớn (Thế Giới Di Động, Thns, TTG, v.v.).
- **Đầu ra:** Các file Excel phân theo từng ngành hàng trong thư mục `notebook-preprocess/`:
  - `phone_data.xlsx`, `laptop_data.xlsx`, `tggd_tablet.xlsx`, `ttg_pc.xlsx`
  - `vga.xlsx`, `ram.xlsx`, `ssd.xlsx`, `banphim.xlsx`, `chuotmaytinh.xlsx`, `tainghe.xlsx`
  - `maygiat.xlsx`, `maylanh.xlsx`, `sacduphong.xlsx`, `adaptersac.xlsx`
  - Kèm theo dữ liệu phản hồi: `tggdcomment.xlsx`.

### 🔹 Bước 2: Tiền xử lý & Hợp nhất Schema (`notebook-preprocess/preprocess_for_all.ipynb`)
- **Mục tiêu:** Đồng bộ cấu trúc dữ liệu không đồng nhất giữa các ngành hàng về một định dạng thống nhất.
- **Nội dung xử lý:**
  1. Kiểm tra cột và chuẩn hóa trường thông tin theo schema: `['id', 'name', 'price', 'image_url', 'category', 'description']`.
  2. Chuẩn hóa giá bán (`normalize_price`): Làm sạch ký tự tiền tệ, dấu chấm, dấu phẩy, đưa về kiểu số nguyên VND.
  3. Tổng hợp thông số kỹ thuật (Attribute aggregation): Gom các cột thông số riêng lẻ của từng loại sản phẩm (CPU, RAM, GPU, Màn hình, Dung lượng pin, Bảo hành,...) thành một trường văn bản `description` dạng `Tên thuộc tính: Giá trị | ...`.
  4. Hợp nhất tất cả các file đã chuẩn hóa thành một file duy nhất: `notebook-preprocess/raw_products.xlsx`.

### 🔹 Bước 3: Tiền xử lý đầu vào cho Pipeline (`scripts/preprocess_csv.py`)
- **Đầu vào:** File `data/raw_products.csv` (hoặc cấu hình trỏ thẳng tới `.xlsx` qua biến `RAW_CSV_FILE` trong `.env`).
- **Nội dung xử lý:**
  - Hỗ trợ đọc cả file `.csv` (UTF-8, UTF-8-SIG) và `.xlsx` (sử dụng engine `openpyxl`).
  - Làm sạch `id`: Loại bỏ phần thập phân `.0` sinh ra do định dạng số của Excel, loại bỏ khoảng trắng dư thừa, ép kiểu chuỗi.
  - Khử trùng lặp (`drop_duplicates` trên cột `id`), chỉ giữ lại bản ghi đầu tiên nếu trùng ID.
  - Xử lý giá trị khuyết (`fillna`): Gán nhãn mặc định cho `name`, `description`, `category`, `image_url`.
  - Chuyển đổi `price` sang số thực / nguyên, thay thế `NaN` bằng `None` (tương đương `null` chuẩn trong JSON).
- **Đầu ra:**
  - `data/raw_products_utf8.csv`: Bản sao CSV chuẩn hóa mã hóa ký tự tiếng Việt.
  - `data/mock_products.json`: Dữ liệu JSON sạch sẵn sàng cho bước embedding.

### 🔹 Bước 4: Tạo Vector Embedding & Cơ Chế Caching (`scripts/embed_to_json.py`)
- **Mô hình AI:** Sử dụng Sentence Transformers với pre-trained model tiếng Việt:
  - Model: `bkai-foundation-models/vietnamese-bi-encoder`
  - Kích thước Vector (`VECTOR_DIM`): 384 chiều.
- **Điểm bổ sung quan trọng - Caching thông minh (`data_hash`):**
  - Tạo mã băm MD5 dựa trên tổ hợp: `id + name + description + category + price + image_url`.
  - So sánh dữ liệu mới với cache trước đó (`data/mock_products_with_embedding.json`).
  - **Chỉ tính toán lại embedding cho sản phẩm mới hoặc sản phẩm có thông tin thay đổi**, giữ nguyên vector đã tính cho các sản phẩm không đổi. Tiết kiệm tối đa thời gian và tài nguyên CPU/GPU.
- **Đầu ra:** `data/mock_products_with_embedding.json` chứa các bản ghi hoàn chỉnh kèm trường `product_embedding` (mảng 384 số thực) và `data_hash`.

### 🔹 Bước 5: Đánh giá mô hình - Tùy chọn (`scripts/evaluate_similarity.py`)
- Script đánh giá chất lượng embedding và mức độ tương đồng giữa các sản phẩm cùng/khác category phục vụ việc kiểm thử offline.

### 🔹 Bước 6: Khởi tạo Schema & Nạp dữ liệu vào Elasticsearch (`scripts/import_to_elasticsearch.py`)
- Kết nối tới cluster Elasticsearch 8.x.
- **Tạo và quản lý 2 Indices:**
  1. **Index `products`:**
     - `product_embedding`: Cấu hình kiểu `dense_vector`, số chiều `384`, độ đo tương đồng `cosine`, thuật toán lập chỉ mục xấp xỉ `HNSW` (`m=16`, `ef_construction=100`).
     - `name`, `description`: Kiểu `text`, analyzer `standard` (phục vụ full-text search).
     - `category`, `id`: Kiểu `keyword` (phục vụ lọc chính xác và gom nhóm).
     - `price`: Kiểu `float` (phục vụ lọc theo khoảng giá).
     - `image_url`, `data_hash`: Kiểu `keyword` với `index: false`.
  2. **Index `click_logs`:**
     - `product_id`: `keyword` (lưu ID sản phẩm được click).
     - `timestamp`: `date` (thời điểm người dùng tương tác).
- **Bulk Indexing:** Sử dụng `elasticsearch.helpers.bulk` nạp nhanh hàng loạt tài liệu từ `mock_products_with_embedding.json` vào index `products`.

### 🔹 Bước 7: Điều phối tự động toàn hệ thống (`run_all.py`)
- Kịch bản orchestrator tập trung:
  - Khởi động Docker containers (`elasticsearch` và `backend`).
  - Polling trạng thái Elasticsearch Health cho tới khi đạt `yellow` hoặc `green`.
  - Tự động gọi tuần tự: `preprocess_csv.py` ➔ `embed_to_json.py` ➔ `import_to_elasticsearch.py`.
  - Cung cấp các tham số linh hoạt: `--no-docker`, `--skip-preprocess`, `--skip-embed`, `--force-embed`, `--stop-after`, `--prune-docker`.

### 🔹 Bước 8: Xây dựng Backend API (FastAPI)
- **Cấu trúc:** `backend/app/main.py` kết hợp tầng xử lý Elasticsearch `backend/app/es_client.py`.
- **Các tính năng & Endpoints chính:**
  - `GET /search-keyword`: Tìm kiếm từ khóa kết hợp bộ lọc danh mục và khoảng giá.
  - `GET /search-semantic-suggestions`: Gợi ý ngữ nghĩa thời gian thực dựa trên kNN vector search (sinh embedding câu query on-the-fly bằng Bi-Encoder).
  - `GET /recommend/{product_doc_id}`: Gợi ý sản phẩm tương tự dựa trên vector của sản phẩm đang xem (Content-Based kNN với `exclude_id` loại trừ chính nó).
  - `GET /products`: Lấy danh sách sản phẩm phân trang (`page`, `size`) kèm lọc theo `category`.
  - `GET /categories`: Lấy danh sách danh mục sản phẩm (sử dụng Elasticsearch Aggregations).
  - `POST /log-click`: Ghi nhận sự kiện click của người dùng vào `click_logs`.
  - **Tích hợp Rating/Popularity Score:** Truy vấn số lượng click từ index `click_logs` để tính số lượt đánh giá / điểm quan tâm (`rating_count`) tự động gắn vào kết quả trả về của từng sản phẩm.
  - **Bộ trích xuất giá tự động bằng NLP Regex (`extract_price_range_from_query`):**
    - Nhận diện các mẫu câu tìm kiếm chứa giá: *"dưới X triệu"*, *"X-Y triệu"*, *"trên X triệu"*, *"từ X triệu"*.
    - Tự động chuyển đổi thành khoảng `(min_price, max_price)` để áp dụng filter trong Elasticsearch mà không cần người dùng chọn bộ lọc thủ công.

### 🔹 Bước 9: Xây dựng Giao diện Người dùng (Frontend)
- **Công nghệ:** HTML5, CSS3 hiện đại, Vanilla JavaScript (`frontend/index.html`, `style.css`, `app.js`).
- **Chức năng giao diện:**
  - Thanh tìm kiếm thông minh với cơ chế Debounce tự động gọi gợi ý ngữ nghĩa.
  - Bộ lọc kết hợp: Danh mục sản phẩm (Category Pills) + Khoảng giá (Price Slider / Presets).
  - Lưới hiển thị sản phẩm (Product Grid) hiển thị ảnh, tên, giá format VND, danh mục và sao đánh giá.
  - Modal xem chi tiết sản phẩm: Hiển thị đầy đủ thông số kỹ thuật trong `description`.
  - Thanh trượt / Danh sách gợi ý "Sản phẩm tương tự" (Related Products) hiển thị ngay trong modal chi tiết.
  - Tự động bắn API `POST /log-click` mỗi khi người dùng click xem chi tiết sản phẩm.

---

## 📝 3. Nhật Ký Thay Đổi & Công Việc Đã Thực Hiện (Changelog)

### [Giai đoạn 1] - Khảo Sát & Thu Thập Dữ Liệu
- [x] Thiết lập kịch bản cào dữ liệu từ các website bán lẻ công nghệ cho hơn 10 danh mục sản phẩm.
- [x] Lưu trữ dữ liệu thô dạng bảng tính Excel trong thư mục `notebook-preprocess/`.
- [x] Thu thập dữ liệu đánh giá, bình luận của khách hàng (`tggdcomment.xlsx`).

### [Giai đoạn 2] - Xây Dựng Notebook Tiền Xử Lý Dữ Liệu
- [x] Xây dựng notebook `preprocess_for_all.ipynb`.
- [x] Xây dựng hàm `normalize_price` xử lý chuỗi tiền tệ tiếng Việt về giá trị số chuẩn.
- [x] Xây dựng logic gộp các trường cấu hình đặc thù của từng danh mục vào cột `description`.
- [x] Kiểm tra schema đồng bộ (`check_excel_column_order`) và gộp toàn bộ thành file tổng `raw_products.xlsx`.

### [Giai đoạn 3] - Tối Ưu Hóa Data Pipeline & Caching Vector
- [x] Viết script `preprocess_csv.py` hỗ trợ đọc cả file `.csv` và `.xlsx` bằng `openpyxl`.
- [x] Xử lý triệt để lỗi ép kiểu ID, khử ID trùng lặp, xử lý các trường rỗng và chuyển đổi `NaN` sang `None` cho JSON.
- [x] Tích hợp thư viện `sentence-transformers` và tải model tiếng Việt `bkai-foundation-models/vietnamese-bi-encoder`.
- [x] Xây dựng cơ chế Caching bằng MD5 Hash (`_create_product_hash`) trong `embed_to_json.py` giúp tránh việc embed lại dữ liệu cũ, tăng tốc độ xử lý nhiều lần.
- [x] Thêm script đánh giá mô hình `evaluate_similarity.py`.

### [Giai đoạn 4] - Thiết Lập Elasticsearch & Lưu Trữ Tương Tác
- [x] Cấu hình Elasticsearch 8.x chạy trên Docker (`docker-compose.yml`) hỗ trợ kNN Vector Search.
- [x] Tạo index `products` với trường `dense_vector` 384 chiều, khoảng cách cosine và thuật toán HNSW.
- [x] Bổ sung index mới `click_logs` để lưu vết lịch sử click xem sản phẩm.
- [x] Viết logic bulk insert nạp dữ liệu nhanh từ file JSON sang Elasticsearch.

### [Giai đoạn 5] - Phát Triển Backend API & Xử Lý Logic Giá
- [x] Khởi tạo FastAPI framework hỗ trợ CORS và mô hình Pydantic.
- [x] Phát triển module kết nối và truy vấn `es_client.py`.
- [x] Tích hợp logic bóc tách khoảng giá từ văn bản tự nhiên bằng Regular Expressions (`PRICE_FILTERING_LOGIC.md`).
- [x] Xây dựng API `/search-keyword`, `/search-semantic-suggestions`, `/recommend/{id}`, `/categories`.
- [x] Bổ sung endpoint `/log-click` và thuật toán tính sao tương tác dựa trên số lượt click thực tế.
- [x] Đóng gói backend vào `Dockerfile` và cấu hình qua `docker-compose.yml`.

### [Giai đoạn 6] - Tự Động Hóa Triển Khai (Orchestrator)
- [x] Xây dựng file điều phối `run_all.py`.
- [x] Tự động khởi động Docker containers, kiểm tra trạng thái sức khỏe của Elasticsearch.
- [x] Chạy tuần tự trọn vẹn pipeline: Preprocess ➔ Embedding ➔ Bulk Import.
- [x] Cung cấp các cờ lệnh tùy chỉnh (`--skip-preprocess`, `--skip-embed`, `--force-embed`, `--prune-docker`).

### [Giai đoạn 7] - Xây Dựng & Tối Ưu Frontend
- [x] Thiết kế giao diện tìm kiếm hiện đại, responsive, hỗ trợ người dùng tìm kiếm theo tên hoặc theo ngữ cảnh giá.
- [x] Tích hợp live suggestions khi người dùng gõ từ khóa tìm kiếm.
- [x] Tích hợp modal chi tiết sản phẩm cùng khối gợi ý Top 5 sản phẩm tương tự bằng thuật toán Content-Based.
- [x] Gắn sự kiện theo dõi hành vi tương tác (Click event tracking) kết nối với backend.

---

## 🚀 4. Hướng Dẫn Vận Hành Nhanh

```bash
# 1. Kích hoạt môi trường ảo
.\venv\Scripts\activate   # Windows

# 2. Chạy toàn bộ quy trình từ khởi động dịch vụ đến nạp dữ liệu:
python run_all.py

# 3. Khởi động nhanh dịch vụ hằng ngày (nếu dữ liệu đã nạp):
docker-compose up -d

# 4. Truy cập các địa chỉ:
# - Giao diện Web: http://localhost:5173/ hoặc mở frontend/index.html
# - Tài liệu API:  http://localhost:8000/docs
# - Elasticsearch: http://localhost:9200/
```
