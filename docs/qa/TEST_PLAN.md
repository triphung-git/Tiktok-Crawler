# TEST PLAN: TIKTOK SPEECH DATA PIPELINE & QUALITY ENGINEERING FRAMEWORK

**Document Version:** 1.2.0  
**Project:** TikTok Speech Data Pipeline (ASR Corpus)  
**Author / Quality Engineer:** Quality Engineering Team  
**Reviewed by:** Tech Lead / QA Lead  
**Target Environment:** Python 3.10+, Playwright Chromium, SQLite, Windows/Linux  

---

## 1. TỔNG QUAN & MỤC TIÊU (INTRODUCTION & OBJECTIVES)

### 1.1 Mục tiêu dự án
Hệ thống xử lý và trích xuất dữ liệu giọng nói từ video ngắn (TikTok Speech Data Pipeline) là một quy trình kỹ thuật cao gồm thu thập dữ liệu (crawling), làm sạch và lọc trùng (data processing), tải và bóc tách âm thanh qua các mô hình AI/ONNX (Deep Learning Media Pipeline), lưu trữ và quản lý dữ liệu (SQLite & JSON Index).

### 1.2 Mục tiêu kiểm thử (Quality Objectives)
1. **Tính đúng đắn chức năng (Functional Correctness):** Đảm bảo 100% video URL được chuẩn hóa, loại bỏ tham số rác và nhận diện phương ngữ chính xác.
2. **Tính toàn vẹn dữ liệu (Data Integrity):** Chặn đứng 100% URL trùng lặp qua 2 tầng (In-batch và Cross-batch Global Index). Đảm bảo cơ sở dữ liệu SQLite tuân thủ các ràng buộc khóa ngoại (Foreign Key) và không có bản ghi mồ côi (Orphan records).
3. **Khả năng chịu lỗi & phục hồi mạng (Resilience & Network Robustness):** Kiểm tra cơ chế tự động thử lại (Retry with Exponential Backoff + Random Jitter) khi gặp mã lỗi HTTP 429 (Rate Limit) hoặc rớt mạng.
4. **An toàn đa luồng & Ghi tệp nguyên tử (Concurrency & Data Consistency):** Xác thực cơ chế Atomic Write (`atomic_write_json`) và Thread Locks không xảy ra xung đột dữ liệu (Race Condition) hoặc file JSON bị hỏng (Unterminated string).
5. **Tự động hóa kiểm thử (Test Automation):** Đạt độ bao phủ mã nguồn (Code Coverage) >= 85% trên toàn bộ các module lõi.

---

## 2. PHẠM VI KIỂM THỬ (TEST SCOPE)

### 2.1 Trong phạm vi (In-Scope)
- **Kiểm thử giao diện tự động (UI Automation Testing):** Sử dụng Playwright theo kiến trúc Page Object Model (POM) để kiểm thử tương tác trên TikTok Web: Search Hashtag, Infinite Scroll, DOM rendering thẻ video, xử lý modal/banner.
- **Kiểm thử giao tiếp API (API & Contract Testing):** Kiểm thử hợp đồng JSON Schema, phản hồi HTTP Status Code, mô phỏng lỗi mạng (429, 404, 500) và xác thực Postman Collection.
- **Kiểm thử cơ sở dữ liệu (Database & SQL Testing):** Kiểm tra cấu trúc bảng SQLite, tính toàn vẹn dữ liệu (Data Integrity), chỉ mục (Indexes) và ràng buộc thời lượng audio.
- **Kiểm thử tích hợp & xử lý dữ liệu (Integration & Pipeline Testing):** Kiểm định 2 tầng lọc trùng lặp, logic phân loại phương ngữ vùng miền, xuất tệp CSV/JSON.
- **Kiểm thử phi chức năng (Non-Functional Testing):**
  - Quản lý tài nguyên RAM khi chạy mô hình AI (< 3.5GB RAM).
  - Khử nhiễu và kiểm tra chuẩn hóa âm thanh theo chuẩn phát thanh quốc tế EBU R128 (-16 LUFS, 16kHz mono).

### 2.2 Ngoài phạm vi (Out-of-Scope)
- Đào tạo lại trọng số mô hình Deep Learning (UVR MDX-Net, Silero VAD, DPDFNet) từ đầu.
- Tải số lượng lớn (> 50.000 video) trong môi trường local mà không có proxy pool quy mô lớn.

---

## 3. CHIẾN LƯỢC KIỂM THỬ (TESTING STRATEGY)

```
       / \
      / E2E \       --> Playwright UI Automation (TikTok Web Search & Scroll)
     /-------\
    /   API   \     --> Postman Collection & Pytest API Contract Validation
   /-----------\
  / Integration \   --> Database SQL Integrity, 2-Tier Deduplication, Pipeline
 /---------------\
/   Unit Tests    \ --> Data Cleaner, Validator, Atomic Write, Exponential Backoff
-------------------
```

### 3.1 Cấp độ kiểm thử (Testing Levels)
1. **Unit Testing:** Kiểm thử đơn vị các hàm làm sạch URL, bóc tách ID, phân loại lỗi retryable, tính toán độ dài câu thoại (sử dụng `pytest`).
2. **Integration Testing:** Kiểm thử tương tác giữa các module: Storage + SQLite + Cleaner; Concurrency Thread Lock + Atomic Write.
3. **Database Testing (SQL):** Thực thi các truy vấn SQL tự động kiểm định: Uniqueness, Not-Null, Referential Integrity giữa `videos` và `segments`.
4. **API Testing:** Kiểm thử hợp đồng JSON Schema dữ liệu đầu vào và các điểm tích hợp API bằng Postman & Pytest.
5. **UI Automation Testing:** Tự động hóa trình duyệt Chromium bằng Playwright kiểm thử tương tác người dùng, xử lý các thách thức WAF / Anti-bot.
6. **Regression Testing:** Chạy toàn bộ test suite tự động qua CI/CD Pipeline (GitHub Actions) trước mỗi lần merge code.

---

## 4. MÔI TRƯỜNG & CÔNG CỤ KIỂM THỬ (TEST ENVIRONMENT & TOOLS)

| Hạng mục | Công cụ / Phiên bản | Mục đích sử dụng |
| :--- | :--- | :--- |
| **Ngôn ngữ** | Python 3.10+ | Môi trường lập trình và thực thi test scripts |
| **Test Runner** | `pytest 8.x+` | Khung thực thi test tự động, assertions, fixtures |
| **UI Automation** | `Playwright 1.43+` | Tự động hóa kiểm thử UI trên Headless/Headed Chromium |
| **API Testing** | `Postman`, `requests`, `jsonschema` | Thiết kế bộ API Collection, assert Schema & Response Time |
| **Database** | SQLite3, DB Browser for SQLite | Thực thi truy vấn kiểm thử toàn vẹn dữ liệu (SQL Testing) |
| **Test Coverage** | `pytest-cov` | Đo lường độ bao phủ mã nguồn (Code Coverage Target: > 85%) |
| **Reporting** | `pytest-html`, Markdown, Allure | Xuất báo cáo kết quả kiểm thử trực quan |
| **CI/CD** | GitHub Actions | Tự động kích hoạt kiểm thử hồi quy trên mỗi Pull Request |

---

## 5. TIÊU CHÍ ĐẦU VÀO VÀ ĐẦU RA (ENTRY & EXIT CRITERIA)

### 5.1 Entry Criteria (Điều kiện bắt đầu kiểm thử)
- Môi trường ảo (`.venv`) đã cài đặt đầy đủ các thư viện trong `requirements.txt`.
- Đã cài đặt Playwright Chromium driver (`playwright install chromium`).
- Các tệp cấu hình `config/settings.yaml` và biến môi trường `.env` hợp lệ.

### 5.2 Exit Criteria (Điều kiện hoàn thành & Bàn giao)
- **100% Test Cases P1 (Critical)** và **P2 (High)** đều đạt trạng thái **PASSED**.
- Không còn bất kỳ lỗi Critical (Blocker) nào tồn đọng.
- Tỷ lệ Code Coverage đạt tối thiểu **85%**.
- Báo cáo kiểm thử (Test Execution Report) và tài liệu Bug Report được nghiệm thu đầy đủ.

---

## 6. QUẢN LÝ LỖI (DEFECT MANAGEMENT WORKFLOW)

Quy trình vòng đời lỗi (Defect Lifecycle) tuân thủ tiêu chuẩn Jira:

```
[New / Open] --> [Assigned] --> [In Progress] --> [Fixed / Resolved] --> [Retest & Verified] --> [Closed]
                                                        |
                                                        +--> [Reopened] (Nếu kiểm thử lại thất bại)
```

- **Mức độ nghiêm trọng (Severity):**
  - **S1 (Blocker/Critical):** Hỏng dữ liệu, deadlock đa luồng, sập tiến trình, rò rỉ bộ nhớ nghiêm trọng.
  - **S2 (Major):** Lỗi lọc trùng lặp thất bại, sai định dạng schema JSON, không bắt được mã lỗi HTTP 429.
  - **S3 (Minor):** Log hiển thị sai định dạng, cảnh báo deprecation, độ trễ xử lý nhẹ.
  - **S4 (Trivial):** Lỗi chính tả trong tài liệu, format hiển thị terminal.
