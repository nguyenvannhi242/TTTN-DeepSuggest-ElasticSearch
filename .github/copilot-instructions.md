# Copilot instructions for DeepSuggest_Elasticsearch

**Purpose**: help an AI code-assistant get productive quickly in this repository — explain the architecture, developer workflows, important conventions, integration points, and fast ways to run and test changes.

**Big Picture**:
- **Backend**: `backend/` is a FastAPI service. Key files: `backend/app/es_client.py` (ES client + embedding model, singleton instance), `backend/app/main.py` (API routes with async/sync handling).
- **Search engine**: Elasticsearch 8.x (v8.11.4) with HNSW vector search. Configured in `docker-compose.yml`. The repo runs ES in Docker and exposes `9200`.
- **Data pipeline**: `scripts/` contains three orchestrated pipeline steps: `preprocess_csv.py` → `embed_to_json.py` → `import_to_elasticsearch.py`. `run_all.py` manages Docker lifecycle + pipeline execution with granular flags.
- **Frontend**: static HTML/CSS/JS demo in `frontend/` (no SPA build system) that calls FastAPI endpoints via JavaScript fetch.

**How the pieces fit (data flow)**:
- Raw CSV → `scripts/preprocess_csv.py` → `data/mock_products.json` (cleaned, deduplicated, UTF-8 safe).
- Embedding generation: `scripts/embed_to_json.py` loads SentenceTransformer model, computes embeddings with caching via `data_hash`. Outputs → `data/mock_products_with_embedding.json` (each product has `data_hash` and `product_embedding` as list).
- Import to ES: `scripts/import_to_elasticsearch.py` creates two indices: (1) `products` with dense_vector mapping, (2) `click_logs` for event tracking. Uses product `id` as Elasticsearch `_id`.
- Runtime: FastAPI loads embeddings once at startup (via `es_client` singleton), exposes endpoints for keyword + semantic kNN search and click logging.
- Click tracking: separate `click_logs` index stores `{ product_id, timestamp }`. Backend provides `/log-click` endpoint.

**Developer workflows / useful commands**:
- **Start services and run pipeline (recommended)**: `python run_all.py` (builds Docker images, starts ES/backend containers, waits for health, runs preprocess → embed → import with error handling). 
  - Useful flags: `--no-docker` (skip Docker, requires manual ES), `--skip-preprocess`, `--only-preprocess`, `--skip-embed`, `--only-embed`, `--force-embed` (delete cache and re-embed), `--stop-after down` (teardown after), `--prune-docker` (cleanup), `--timeout-es 300` (ES health timeout).
- **Quick dev iteration (Docker already running)**: `docker-compose up -d` then `docker-compose restart backend` after code changes (rebuilds backend image).
- **Build backend only**: `docker-compose build backend`.
- **Inspect Elasticsearch**: `http://localhost:9200/_cat/indices?v` (list indices) or use Kibana at `http://localhost:5601`.
- **FastAPI auto-docs**: `http://localhost:8000/docs` (Swagger UI with all endpoints).

**Project-specific conventions & patterns**:
- Product documents use the original `id` as the Elasticsearch document `_id` (see `generate_bulk_actions` in `scripts/import_to_elasticsearch.py`). Treat `id` as string.
- Embedding caching: `embed_to_json.py` adds `data_hash` to avoid recomputing embeddings when product content hasn't changed. `EMBEDDED_JSON_FILE` stores `product_embedding` as a list.
- The ES mapping uses a `dense_vector` field named `product_embedding`. Vector dimension is controlled by `VECTOR_DIM` env var and must match the embedding model output.
- Click logging: a separate index `click_logs` stores events with `product_id` (the ES doc id) and `timestamp`. Backend provides `/log-click` to write events.
- The backend loads the SentenceTransformer model at import-time inside `es_client.py` — this blocks startup and may fail if model download is slow. Use `MODEL_NAME` env var to control the model.

**Important environment variables (.env)**
- `ELASTICSEARCH_HOST` (default `http://localhost:9200`)
- `INDEX_NAME` (default `products`)
- `MODEL_NAME` (embedding model id/name used by `SentenceTransformer`)
- `VECTOR_DIM` (int, must match model output length)
- File toggles: `RAW_CSV_FILE`, `PREPROCESSED_JSON_FILE`, `EMBEDDED_JSON_FILE`

**API surfaces to know (examples)**:
- `GET /search-keyword?query=...` — keyword search on text fields (see `es_client.keyword_search`).
- `GET /search-semantic-suggestions?query=...` — embeds query, returns kNN results via ES (see `es_client.semantic_search_suggestions`).
- `GET /recommend/{product_doc_id}` — returns product by id + kNN recommendations (uses `es_client.knn_search`).
- `POST /log-click` — accepts JSON `{ "product_id": "..." }`, writes to `click_logs` index (see `es_client.log_click`).

**Files to inspect when changing behavior**
- `backend/app/es_client.py` — ES client, model loading, search logic, click-aggregation helpers.
- `backend/app/main.py` — routes and simple orchestration of `es_client` calls.
- `scripts/*.py` — pipeline steps (preprocess/embed/import). `run_all.py` orchestrates these steps and Docker lifecycle.
- `docker-compose.yml` — service definitions and ES healthcheck (backend depends on ES healthy state).

**Common pitfalls & notes for an AI assistant**
- Model loading is performed at module import in `es_client.py`. Avoid editing runtime assumptions without considering container startup time and model download size.
- `product_embedding` is stored as a Python list in JSON and mapped to ES `dense_vector`. Ensure `VECTOR_DIM` and the model output shape match before import.
- `import_to_elasticsearch.py` **does not** delete existing `products` index by default — it will skip creating if present to preserve `click_logs`. Be cautious when reindexing.
- When running locally outside Docker, ensure `ELASTICSEARCH_HOST` points to your ES instance and `run_all.py` flags (`--no-docker`) are used appropriately.

If anything above is unclear or you'd like the instructions tuned to a different workflow (for example: pure local dev without Docker, VS Code debug configuration, or adding unit tests), tell me which area to expand and I will update this file.
