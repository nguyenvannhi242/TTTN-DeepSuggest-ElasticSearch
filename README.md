# 🧠 Hệ thống Gợi ý Sản phẩm (Elasticsearch + Embedding)

Dự án demo **gợi ý sản phẩm tương tự (Content-Based Recommendation)** bằng **vector embedding** được tính toán offline và tìm kiếm bằng **kNN trên Elasticsearch**.
Kiến trúc gồm:

* 🧩 **Backend:** FastAPI (nhẹ, RESTful)
* 🎨 **Frontend:** HTML / CSS / JS
* 🔍 **Search Engine:** Elasticsearch 8.x

---

## 🏗️ Cấu trúc Thư mục

```bash
├── 📁 backend
│   ├── 📁 app
│   │   ├── __init__.py
│   │   ├── es_client.py
│   │   └── main.py
│   ├── Dockerfile
│   └── requirements.txt
├── 📁 data
│   ├── mock_products.json
│   ├── mock_products_with_embedding.json
│   └── raw_products.csv
├── 📁 frontend
│   ├── index.html
│   ├── style.css
│   └── app.js
├── 📁 scripts
│   ├── embed_to_json.py
│   ├── evaluate_similarity.py
│   ├── import_to_elasticsearch.py
│   ├── preprocess_csv.py
│   └── requirements.txt
├── .gitignore
├── docker-compose.yml
├── run_all.py
└── README.md
```

---

## ⚙️ Yêu cầu Hệ thống

* **Python:** 3.10 (nên trùng với bản trong Dockerfile)
* **Docker & Docker Compose:** cài đặt và khởi động Docker Desktop
* **Git:** *(tùy chọn)* để quản lý mã nguồn

---

## 🚀 Cài đặt Ban đầu

### 1️⃣ Di chuyển đến thư mục dự án

```bash
cd TTTN
```

### 2️⃣ Tạo và kích hoạt môi trường ảo

```bash
python -m venv venv
```

**Windows:**

```bash
.\venv\Scripts\activate
```

**macOS / Linux:**

```bash
source venv/bin/activate
```

> Xuất hiện `(venv)` đầu dòng nghĩa là đã kích hoạt thành công.

---

### 3️⃣ Cài đặt thư viện cần thiết

```bash
pip install -r scripts/requirements.txt
pip install "setuptools<58"
```

---

### 4️⃣ Chuẩn bị dữ liệu

Đặt file dữ liệu gốc vào thư mục `data/`:

```
data/raw_products.csv
```

---

### 5️⃣ Cấu hình môi trường `.env`

Tạo file `.env` tại thư mục gốc (hoặc sao chép từ `.env.example`) và thêm:

```
ES_HOST=http://localhost:9200
INDEX_NAME=products
EMBEDDING_MODEL=...
```

---

### 6️⃣ Build Docker Image (lần đầu)

```bash
docker-compose build --no-cache
```

> Chỉ cần build lại khi thay đổi `Dockerfile` hoặc `backend/requirements.txt`.

---

## ▶️ Chạy & Quản lý Ứng dụng

### 🧩 1. Chạy toàn bộ pipeline

```bash
python run_all.py
```

Chạy trọn quy trình:

* Khởi động Docker (Elasticsearch + Backend)
* Xử lý dữ liệu (preprocess → embed → import)

> Dùng khi cài đặt lần đầu hoặc có dữ liệu mới.

---

### ⚡ 2. Khởi động dịch vụ Docker (sử dụng hằng ngày)

```bash
docker-compose up -d
```

> `-d` giúp chạy nền (background).

---

### 🔁 3. Cập nhật code backend

```bash
docker-compose build backend
docker-compose up -d
```

> Không cần chạy lại `run_all.py` nếu dữ liệu không đổi.

---

### 🔄 4. Khởi động lại Backend

```bash
docker-compose restart backend
```

---

### 🛑 5. Dừng ứng dụng

```bash
docker-compose down
```

Nếu muốn xóa luôn dữ liệu Elasticsearch:

```bash
docker-compose down -v
```

---

## 🧹 Dọn dẹp Docker

**Cơ bản (nên dùng thường xuyên):**

```bash
docker system prune -f
```

**Toàn bộ (xóa cả cache và image cũ):**

```bash
docker system prune -a -f
```

> Có thể dùng `python run_all.py --prune-docker` để dọn tự động sau khi chạy.

---

## 📊 Đánh giá Mô hình (Tùy chọn)

```bash
python scripts/evaluate_similarity.py
```

> Yêu cầu `numpy` và `ml_metrics` trong `venv`.

---

## 💡 Kiểm tra Nhanh

* Kiểm tra Elasticsearch:
  👉 [http://localhost:9200/_cat/indices?v](http://localhost:9200/_cat/indices?v)

* Kiểm tra Backend (FastAPI docs):
  👉 [http://localhost:8000/docs](http://localhost:8000/docs)

  **Truy cập:**
    * **Trang web:** `http://localhost:5173/` (Hoặc mở file `frontend/index.html`)
    * **Backend API Docs:** `http://localhost:8000/docs`
    * **Kibana (Xem data):** `http://localhost:5601`
---

## 🎯 Kết luận

Dự án minh họa quy trình **xây dựng hệ thống gợi ý sản phẩm dựa trên nội dung (Content-Based Recommendation)** gồm:

1. Tiền xử lý dữ liệu
2. Tính toán vector embedding
3. Lưu & tìm kiếm bằng Elasticsearch
4. Kết hợp Backend API + Frontend hiển thị kết quả

> 🎯 Giúp hiểu trọn luồng triển khai thực tế của hệ thống gợi ý hiện đại.



docker-compose exec elasticsearch curl -X DELETE "localhost:9200/products,click_logs"