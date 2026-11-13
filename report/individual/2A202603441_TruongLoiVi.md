# Báo cáo thực nghiệm cá nhân – Lab 6: Data Ingestion Engineering

**Học viên:** Trương Lợi Vĩ
**MSSV:** 2A202603441
**Lớp:** L3A
**Chủ đề:** Generative AI and AI Literacy in Higher Education
**Repo:** https://github.com/ViTL-AI26/K5-L3A-DAY06-2A202603441-DataIngestion

## 1. Mục tiêu

Thực nghiệm xây dựng pipeline ingestion và retrieval cho corpus về Generative AI và AI literacy trong giáo dục đại học. Ba chiến lược A/B/C được so sánh để xem xét ảnh hưởng của cách chia chunk và metadata filtering đến khả năng truy xuất bằng chứng. Các chiến lược sử dụng cùng corpus, benchmark, embedding model và vector store nhằm giữ tính công bằng khi so sánh.

## 2. Corpus và benchmark

Corpus gồm **58 trang nội dung hợp lệ**, tổng cộng **217.038 ký tự**, từ ba tài liệu:

| Source ID | Tài liệu | Năm | Trang được chọn | Quyền sử dụng |
|---|---|---:|---:|---|
| `unesco_genai_2023` | UNESCO, *Guidance for Generative AI in Education and Research* | 2023 | 10–41 (32 trang) | CC BY-SA 3.0 IGO |
| `educause_horizon_2024` | EDUCAUSE, *2024 EDUCAUSE Horizon Report: Teaching and Learning* | 2024 | 19–25 và 44 (8 trang) | CC BY-NC-ND 4.0 International |
| `odea_ai_literacy_2024` | O’Dea et al., *Factors Affecting University Students' Generative AI Literacy: Evidence and Evaluation in the UK* | 2024 | 2–19 (18 trang) | Giới hạn tái sử dụng; không có giấy phép mở cho phép phân phối lại tùy ý |

Quy tắc đếm loại trừ bìa, mục lục, trang trắng và trang chỉ có tài liệu tham khảo. Các trang được chọn đã được trích xuất và kiểm tra có nội dung.

Benchmark có **20 câu hỏi**, chia thành **15 dev và 5 test** trước khi chạy thực nghiệm. Có 4 câu hỏi có metadata filter, trong đó có câu thuộc tập test. Mỗi câu hỏi có expected answer, gold source, gold page và evidence quote.

## 3. Thiết lập hệ thống

- Embedding model: `text-embedding-3-small`.
- Kích thước vector: 768 chiều.
- Vector store: PostgreSQL với extension pgvector.
- Similarity: cosine similarity.
- Metadata gồm các trường định danh tài liệu/nguồn/trang và các thuộc tính như `year`, `topic`, `title`, `license`, `source_id`, `chunking_method`, `chunk_index`.
- Cùng embedding model, corpus và benchmark được sử dụng cho cả ba chiến lược.

## 4. Thiết kế ba chiến lược

| Strategy | Cách chia chunk | Kích thước | Overlap | Filter |
|---|---|---:|---:|---|
| A | Fixed-size | 500 ký tự | 50 ký tự | Không |
| B | Paragraph-aware, gom đoạn theo giới hạn | Tối đa 500 ký tự | Không áp dụng | Không |
| C | Dùng lại chunks của B | Tối đa 500 ký tự | Không áp dụng | Áp dụng khi câu hỏi có filter |

A–B là phép so sánh tập trung vào cách chia chunk. B–C giữ nguyên chunks/embeddings và thay đổi việc áp dụng metadata filter. C tái sử dụng vectors của B, vì vậy không phát sinh lần embedding mới trong lần chạy này.

## 5. Kết quả retrieval

Evidence Hit@3 được tính khi top-3 có chunk cung cấp bằng chứng phù hợp với gold source/page và đủ nội dung theo tiêu chí đánh giá nghiêm ngặt.

| Strategy | Split | Hit@1 | Evidence Hit@3 |
|---|---|---:|---:|
| A | Dev (n=15) | 2/15 (13,33%) | 5/15 (33,33%) |
| B | Dev (n=15) | 4/15 (26,67%) | 5/15 (33,33%) |
| C | Dev (n=15) | 4/15 (26,67%) | 5/15 (33,33%) |
| A | Test (n=5) | 1/5 (20,00%) | 2/5 (40,00%) |
| B | Test (n=5) | 1/5 (20,00%) | 2/5 (40,00%) |
| C | Test (n=5) | 1/5 (20,00%) | 2/5 (40,00%) |

### Phân tích

- **A → B:** Hit@1 trên dev tăng từ 13,33% lên 26,67%. Evidence Hit@3 không thay đổi. Điều này gợi ý paragraph-aware chunking có thể đưa chunk liên quan lên vị trí đầu, nhưng chưa tăng số câu có đủ bằng chứng trong top-3.
- **B → C:** Không ghi nhận thay đổi ở Hit@1 hoặc Evidence Hit@3 trên dev/test.
- Trên test, cả ba chiến lược có kết quả như nhau. Với chỉ 5 câu test, không nên khái quát hóa kết quả thành hiệu suất tổng thể.
- Một số trường hợp có bằng chứng bị chia qua ranh giới chunk. Hệ thống có thể truy xuất nội dung liên quan nhưng không chứa trọn evidence quote trong một chunk, dẫn đến không đạt tiêu chí strict evidence hit.

## 6. Đánh giá năm khía cạnh

### 6.1 Retrieval accuracy

Các chỉ số Hit@1 và Evidence Hit@3 được báo cáo riêng cho dev/test ở Bảng 5. B cải thiện Hit@1 trên dev so với A, nhưng không cải thiện Evidence Hit@3. Kết quả test không phân biệt được ba chiến lược.

### 6.2 Chunk coherence

Đánh giá mẫu thủ công trên 10 vị trí nguồn cho mỗi chiến lược, thang điểm 0–2 (0: không mạch lạc; 1: có ý nghĩa nhưng thiếu một phần ngữ cảnh; 2: mạch lạc và giữ được ý chính).

| Strategy | Tổng điểm | Trung bình /2 |
|---|---:|---:|
| A | 8/20 | 0,80 |
| B | 10/20 | 1,00 |
| C | 10/20 | 1,00 |

B và C có cùng cách chia chunk nên điểm coherence giống nhau. B/C tốt hơn A trong mẫu đánh giá này, nhưng điểm trung bình vẫn ở mức vừa phải.

### 6.3 Metadata usefulness

Kiểm tra 45 bản ghi (5 câu test × top-3 × 3 chiến lược). Cả A, B và C đều có 15/15 bản ghi đạt kiểm tra đầy đủ các trường metadata bắt buộc, tương đương 100%. Với các câu có filter, kiểm tra thêm điều kiện filter trên kết quả trả về. Đây là kiểm tra tính đầy đủ và tuân thủ metadata/filter, không phải xác nhận ngữ nghĩa độc lập cho mọi giá trị metadata.

### 6.4 Grounding quality

Đánh giá thủ công top-3 của 5 câu test cho mỗi chiến lược, tổng 15 kết quả/chiến lược. Thang điểm 0–2: 0 = không hỗ trợ; 1 = liên quan nhưng chưa đủ/không khớp hoàn toàn nguồn-trang; 2 = bằng chứng trực tiếp và đủ hỗ trợ.

| Strategy | Tổng điểm | Trung bình /2 |
|---|---:|---:|
| A | 14/30 | 0,93 |
| B | 14/30 | 0,93 |
| C | 14/30 | 0,93 |

Điểm trung bình bằng nhau nhưng vị trí các bằng chứng đạt điểm khác nhau giữa các chiến lược. Một số chunk chỉ chứa một phần yêu cầu của câu hỏi hoặc bằng chứng bị chia qua ranh giới chunk.

### 6.5 Strategy impact

- B giảm số chunks từ 505 xuống 466 (giảm khoảng 7,72%) và tăng điểm coherence từ 0,80 lên 1,00.
- B cải thiện dev Hit@1 nhưng không cải thiện Evidence Hit@3 hoặc test metrics.
- C chứng minh pipeline có thể áp dụng metadata filter, nhưng bộ lọc `year=2024` chưa đủ phân biệt trong benchmark hiện tại vì cả EDUCAUSE và O’Dea đều xuất bản năm 2024. Do đó, B và C cho kết quả retrieval giống nhau.
- Không có chiến lược thắng trên tất cả tiêu chí. B có triển vọng khi ưu tiên tính mạch lạc; C hữu ích về mặt chức năng khi cần lọc metadata, nhưng cần thuộc tính phân biệt tốt hơn.

## 7. Tài nguyên và thời gian

| Chỉ số | A | B | C |
|---|---:|---:|---:|
| Số chunks | 505 | 466 | 466 |
| Tổng ký tự trong chunks | 239.269 | 216.630 | 216.630 |
| Độ dài nhỏ nhất | 60 | 8 | 8 |
| Độ dài lớn nhất | 500 | 500 | 500 |
| Độ dài trung bình | 473,80 | 464,87 | 464,87 |
| Trung vị | 500 | 495 | 495 |
| Chunking time (s) | 0,001 | 0,013 | 0,000 |
| Embedding time (s) | 5,433 | 5,498 | 0,000 |
| Storage time (s) | 0,718 | 0,726 | 0,387 |

C tái sử dụng chunks và vectors của B; thời gian embedding bằng 0 là do không gọi embedding lại. Thời gian thực thi có thể phụ thuộc môi trường và không đại diện cho benchmark hiệu năng tổng quát. Chi phí API bằng tiền, kết quả kiểm tra idempotent re-ingestion và số lượng ingestion failures không được ghi nhận riêng trong resource summary; báo cáo không suy diễn các giá trị này thành 0 hoặc thành công.

## 8. Hạn chế và hướng cải thiện

1. Test chỉ có 5 câu hỏi, nên độ tin cậy và khả năng khái quát còn hạn chế.
2. Một số evidence quote bị chia qua ranh giới chunk. Có thể thử điều chỉnh quy tắc gom đoạn hoặc bổ sung multi-chunk evidence aggregation.
3. Paragraph chunking có một số chunk rất ngắn (min 8 ký tự); cần kiểm tra và cân nhắc xử lý các đoạn quá ngắn.
4. Filter `year=2024` chưa có tính phân biệt đủ cao. Có thể bổ sung metadata cụ thể hơn như document type hoặc topic chi tiết, đồng thời thiết kế câu hỏi/filter phù hợp.
5. Các điểm coherence và grounding là đánh giá có hỗ trợ phân tích nội dung và mang tính chủ quan; cần người đánh giá rà soát trước khi xem là audit độc lập.
6. Chi phí API, idempotency và ingestion failures chưa có số liệu được lưu trong resource summary.

## 9. Kết luận

Trong thực nghiệm này, paragraph-aware chunking (B) cho coherence cao hơn fixed-size chunking (A), giảm số chunks và cải thiện Hit@1 trên dev. Tuy nhiên, chưa có cải thiện ở Evidence Hit@3 hoặc tập test. Metadata filtering (C) được áp dụng mà không cần embedding lại, nhưng chưa tạo khác biệt retrieval do filter hiện tại chưa đủ phân biệt các nguồn.

Vì vậy, không có chiến lược nào vượt trội trên mọi tiêu chí. B là lựa chọn có triển vọng khi ưu tiên giữ ngữ cảnh đoạn văn; C phù hợp khi hệ thống cần lọc metadata, với điều kiện metadata/filter được thiết kế có tính phân biệt cao hơn. Các kết luận cần được xem xét trong giới hạn của benchmark nhỏ và các đánh giá thủ công.

## 10. Tái lập thực nghiệm

Chạy từ thư mục `starter/` theo hướng dẫn trong README. Cần cấu hình `DATABASE_URL`, `OPENAI_API_KEY` và `EMBEDDING_MODEL=text-embedding-3-small` trong file `.env` cục bộ. Không đưa `.env` hoặc API key lên GitHub. Pipeline có thể gọi embedding API và phát sinh chi phí khi chạy lại; các kết quả trong báo cáo là kết quả đã lưu, không cần chạy lại để đọc báo cáo.
