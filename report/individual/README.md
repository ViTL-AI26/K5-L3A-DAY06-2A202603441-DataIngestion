# Lab 6 – Data Ingestion Engineering

**Học viên:** Trương Lợi Vĩ – 2A202603441 – L3A
**Chủ đề:** Generative AI and AI Literacy in Higher Education
**Repository:** https://github.com/ViTL-AI26/K5-L3A-DAY06-2A202603441-DataIngestion

## Nội dung

- `starter/`: source code, corpus manifest, benchmark và pipeline.
- `artifacts/experiment_log.csv`: cấu hình và giả thuyết của A/B/C.
- `results/`: kết quả retrieval, tài nguyên và audit.
- `report/individual/2A202603441_TruongLoiVi.md`: báo cáo cá nhân.

## Yêu cầu môi trường

- Python 3
- Docker và Docker Compose
- PostgreSQL với pgvector (pipeline đã được kiểm tra với PostgreSQL 16 và pgvector 0.8.7)
- OpenAI API key có quyền sử dụng `text-embedding-3-small`

## Cấu hình

Tạo file `starter/.env` từ máy cá nhân, không commit file này:

```dotenv
DATABASE_URL=postgresql://<user>:<password>@localhost:55433/day6_lab
OPENAI_API_KEY=<your_openai_api_key>
EMBEDDING_MODEL=text-embedding-3-small
```

Điền thông tin kết nối đúng với cấu hình trong `starter/docker-compose.yml` (nếu khác). Không chia sẻ API key.

## Cài đặt và chạy

Từ thư mục gốc repository:

```bash
cd starter
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Khởi động dịch vụ PostgreSQL/pgvector theo compose file của starter:

```bash
docker compose up -d
```

Kiểm tra kết nối và extension:

```bash
python scripts/check_setup.py
```

Chạy pipeline từ thư mục `starter/`:

```bash
python -m src.run
```

**Lưu ý:** pipeline gọi embedding API. Chạy lại có thể phát sinh chi phí. Kết quả đã lưu trong `results/` có thể được đọc mà không cần chạy lại.

## Dữ liệu và kết quả

- Manifest: `starter/data/manifest.json`
- Benchmark: `starter/data/benchmark.json`
- Experiment log: `artifacts/experiment_log.csv`
- Kết quả lưu trong repo: `results/`
- Báo cáo: `report/individual/2A202603441_TruongLoiVi.md`

Theo mã pipeline, khi chạy từ `starter/`, output mặc định được ghi vào `artifacts/day06/` ở thư mục cha của `starter/`. Các file đã được sao chép vào `results/` để tiện nộp và kiểm tra.

## Thiết kế thực nghiệm

- A: fixed-size, 500 ký tự, overlap 50.
- B: paragraph-aware, giới hạn 500 ký tự.
- C: tái sử dụng chunks/vectors của B và áp dụng metadata filter khi câu hỏi có filter.

Cả ba dùng cùng corpus, benchmark, embedding model và pgvector store.

## Quyền sử dụng dữ liệu và lưu ý chia sẻ

Manifest ghi nguồn, giấy phép/quyền sử dụng và trang được chọn. Một nguồn trong corpus có điều kiện tái sử dụng hạn chế. Trước khi để repository ở chế độ public, cần kiểm tra trace và các file kết quả có chứa đoạn trích dài/nội dung không được phép phân phối lại hay không. Không commit PDF/tài liệu gốc hoặc nội dung bị hạn chế nếu không có quyền. Nếu cần, chỉ chia sẻ metadata, câu trích dẫn ngắn được phép và hướng dẫn tái tạo/kiểm chứng cho người chấm.

## Bảo mật

Không commit `.env`, API key, mật khẩu database, `.venv/`, cache hoặc dữ liệu cá nhân. Kiểm tra `git status` trước khi commit.
