# TEST CASES SPECIFICATION MATRIX

**Project:** TikTok Speech Data Pipeline & Quality Engineering Framework  
**Document Code:** TC-MAT-01  
**Total Test Cases:** 35 Test Cases  
**Author:** Software Quality Engineer (QE)  
**Status:** Approved & Implemented  

---

## 1. TỔNG HỢP TRẠNG THÁI KIỂM THỬ (TEST SUMMARY)

| Phân loại kiểm thử (Test Category) | Số lượng TC | Priority (P1/P2/P3) | Automated | Tình trạng |
| :--- | :---: | :---: | :---: | :---: |
| **Functional Testing (Data Processing & Cleaner)** | 10 | 6 P1 / 4 P2 | 10/10 | **PASSED** |
| **Data Integrity & SQL Database Testing** | 6 | 4 P1 / 2 P2 | 6/6 | **PASSED** |
| **API & Contract Testing** | 6 | 4 P1 / 2 P2 | 6/6 | **PASSED** |
| **UI Automation Testing (Playwright)** | 5 | 3 P1 / 2 P2 | 5/5 | **PASSED** |
| **Resilience & Error Handling (Retry/429)** | 4 | 3 P1 / 1 P2 | 4/4 | **PASSED** |
| **Concurrency & Non-Functional Testing** | 4 | 3 P1 / 1 P2 | 4/4 | **PASSED** |
| **TỔNG CỘNG** | **35** | **23 P1 / 12 P2** | **35/35 (100%)** | **PASSED** |

---

## 2. MA TRẬN TEST CASES CHI TIẾT (DETAILED TEST CASES MATRIX)

### NHÓM 1: FUNCTIONAL TESTING - DATA PROCESSING & VALIDATION

| Test Case ID | Tên kịch bản (Scenario) | Điều kiện tiên quyết (Pre-conditions) | Các bước thực hiện (Steps to Reproduce) | Dữ liệu đầu vào (Test Data) | Kết quả mong đợi (Expected Result) | Trạng thái |
| :--- | :--- | :--- | :--- | :--- | :--- | :---: |
| **TC-FUNC-01** | Kiểm tra nhận diện nền tảng từ URL hợp lệ | Module cleaner đã nạp cấu hình regex | Truyền URL TikTok vào hàm `detect_platform()` | `https://www.tiktok.com/@user/video/7234567890123456789` | Trả về chuỗi `"tiktok"` | **PASS** |
| **TC-FUNC-02** | Xử lý URL nền tảng không hỗ trợ | Module cleaner hoạt động | Truyền URL Youtube/Facebook vào `detect_platform()` | `https://www.youtube.com/watch?v=dQw4w9WgXcQ` | Trả về `"unknown"` hoặc ném ngoại lệ phân loại | **PASS** |
| **TC-FUNC-03** | Làm sạch URL chứa tham số tracking rác | Hàm `sanitize_video_url()` khả dụng | Truyền URL chứa tham số UTM, referrer, tracking vào hàm | `https://www.tiktok.com/@vtv24/video/7123?is_from_webapp=1&sender_device=pc&utm_source=share` | URL được chuẩn hóa thành `https://www.tiktok.com/@vtv24/video/7123` | **PASS** |
| **TC-FUNC-04** | Trích xuất ID video chính xác | URL chuẩn TikTok | Gọi hàm `extract_video_id()` | `https://www.tiktok.com/@vtv24/video/7123456789012345678` | Trả về chuỗi ID `"7123456789012345678"` | **PASS** |
| **TC-FUNC-05** | Suy luận phương ngữ Bắc (Northern Dialect) | Từ điển tag/location khả dụng | Truyền text chứa từ khóa Hà Nội, miền Bắc vào hàm `infer_regional_dialect()` | `"Bản tin thời sự Hà Nội sáng nay"` | Trả về nhãn `"northern"` | **PASS** |
| **TC-FUNC-06** | Suy luận phương ngữ Nam (Southern Dialect) | Từ điển tag/location khả dụng | Truyền text chứa từ khóa Sài Gòn, TP.HCM, miền Tây | `"Đặc sản Sài Gòn ăn là mê"` | Trả về nhãn `"southern"` | **PASS** |
| **TC-FUNC-07** | Nhận diện phương ngữ không xác định | Text không chứa từ khóa định danh | Truyền text chung chung không chứa từ khóa vùng miền | `"Hôm nay trời đẹp quá bạn ơi"` | Trả về nhãn `"unidentified"` | **PASS** |
| **TC-FUNC-08** | Lọc bỏ ký tự đặc biệt & emoji trong text | Hàm `clean_text()` sẵn sàng | Truyền chuỗi chứa icon cảm xúc, xuống dòng, khoảng trắng thừa | `"Tin vui cực hot 🔥🔥🔥 !!!\n\nXem ngay   ạ"` | Trả về text sạch `"Tin vui cực hot !!! Xem ngay ạ"` | **PASS** |
| **TC-FUNC-09** | Xác thực định dạng tên Batch hợp lệ | Hàm `validate_batch_name()` khả dụng | Kiểm tra chuỗi batch theo quy ước `WEEK<N>_<DDMM>` | `"WEEK3_0309"` | Trả về `True` (Valid) | **PASS** |
| **TC-FUNC-10** | Từ chối định dạng tên Batch sai quy ước | Hàm `validate_batch_name()` khả dụng | Kiểm tra chuỗi batch sai format | `"batch_hom_nay_01"`, `""`, `"WEEK_ABC"` | Trả về `False` kèm thông báo lỗi cấu trúc | **PASS** |

---

### NHÓM 2: DATA INTEGRITY & DATABASE TESTING (SQL)

| Test Case ID | Tên kịch bản | Điều kiện tiên quyết | Các bước thực hiện | Dữ liệu đầu vào | Kết quả mong đợi (Expected Result) | Trạng thái |
| :--- | :--- | :--- | :--- | :--- | :--- | :---: |
| **TC-DB-01** | Kiểm tra tính duy nhất (Uniqueness) trong Global Index | SQLite Database đã khởi tạo | Chèn 2 bản ghi có cùng một `url` vào bảng `global_index` | `url = 'https://tiktok.com/@test/123'` (Insert 2 lần) | Ràng buộc `PRIMARY KEY` chặn bản ghi thứ 2 hoặc thay thế hợp lệ, không có duplicate URL | **PASS** |
| **TC-DB-02** | Ràng buộc khóa chính bảng `videos` (`task_id`) | Database kết nối thành công | Gọi `insert_task()` với `task_id` đã tồn tại | Cùng một `task_id = 'TASK_0001'` với status mới | Hệ thống thực hiện `INSERT OR REPLACE`, bảo toàn 1 bản ghi duy nhất | **PASS** |
| **TC-DB-03** | Kiểm tra toàn vẹn liên kết khóa ngoại (`Foreign Key`) | Bảng `videos` và `segments` liên kết | Kiểm tra truy vấn SQL tìm các phân đoạn âm thanh mồ côi | `SELECT * FROM segments s LEFT JOIN videos v ON s.task_id = v.task_id WHERE v.task_id IS NULL` | Trả về 0 dòng (Không có phân đoạn nào không có task cha) | **PASS** |
| **TC-DB-04** | Ràng buộc thời lượng phân đoạn âm thanh (Business Rule) | Dữ liệu segments đã insert | Truy vấn các phân đoạn có thời lượng nằm ngoài ngưỡng chuẩn ASR | `SELECT * FROM segments WHERE duration < 2.0 OR duration > 15.0` | Trả về 0 dòng (100% audio segments đạt chuẩn 2s đến 15s) | **PASS** |
| **TC-DB-05** | Kiểm tra các trường dữ liệu bắt buộc (NOT NULL) | Database đã ghi nhận tasks | Truy vấn các task có trạng thái hoặc URL bị `NULL` | `SELECT COUNT(*) FROM videos WHERE original_url IS NULL OR status IS NULL` | Trả về kết quả đếm bằng 0 | **PASS** |
| **TC-DB-06** | Hiệu năng tìm kiếm chỉ mục (Index Performance) | Bảng có dữ liệu lớn | Chạy `EXPLAIN QUERY PLAN` trên truy vấn theo `crawl_batch` | `SELECT * FROM videos WHERE crawl_batch = 'WEEK3_0309'` | Kế hoạch thực thi xác nhận sử dụng `INDEX idx_videos_batch` (Không Scan toàn bảng) | **PASS** |

---

### NHÓM 3: API & CONTRACT TESTING (POSTMAN & PYTEST)

| Test Case ID | Tên kịch bản | Điều kiện tiên quyết | Các bước thực hiện | Dữ liệu đầu vào | Kết quả mong đợi (Expected Result) | Trạng thái |
| :--- | :--- | :--- | :--- | :--- | :--- | :---: |
| **TC-API-01** | Kiểm tra hợp đồng JSON Schema cho Crawled Item | Postman / Pytest Runner | Gửi payload hoặc mock JSON của Scrapy Item qua bộ validator | Payload từ Scrapy Item (`url`, `title`, `duration`, `author`) | Schema khớp 100% với JSON Schema v4 (Đủ trường, đúng type) | **PASS** |
| **TC-API-02** | Xử lý phản hồi thành công HTTP Status 200 | Môi trường mạng hoặc Mock Server | Gửi GET request đến API metadata video | Mock endpoint `/api/video/detail?id=123` | Status code trả về `200 OK`, response body chứa `aweme_id` | **PASS** |
| **TC-API-03** | Bắt lỗi và xử lý mã lỗi HTTP 429 Rate Limit | Trình tải `audio_downloader` | Giả lập response HTTP 429 Too Many Requests | Mock request trả về `429 Too Many Requests` | Hàm `classify_error()` nhận diện là `RateLimitError` và kích hoạt retry | **PASS** |
| **TC-API-04** | Kiểm tra thời gian phản hồi API (Response Time SLA) | Postman Test Suite | Thực hiện request và đo lường thời gian phản hồi | Postman test script: `pm.expect(pm.response.responseTime).to.be.below(800)` | Thời gian phản hồi nằm trong ngưỡng cho phép (< 800ms) | **PASS** |
| **TC-API-05** | Xử lý lỗi Token Media hết hạn (HTTP 403 Forbidden) | Trình tải audio | Mock link CDN âm thanh trả về 403 do hết hạn chữ ký | CDN URL với token cũ | Nhận diện lỗi và log rõ ràng trạng thái không thể retry | **PASS** |
| **TC-API-06** | Xác thực hợp đồng đầu ra `sources_<batch>.json` | Pipeline hoàn tất khâu URL | Kiểm tra tệp JSON xuất ra cho worker xử lý audio | Tệp `sources_0309.json` | Đầy đủ các trường: `task_id`, `url`, `platform`, `duration`, `region` | **PASS** |

---

### NHÓM 4: UI AUTOMATION TESTING (PLAYWRIGHT)

| Test Case ID | Tên kịch bản | Điều kiện tiên quyết | Các bước thực hiện | Dữ liệu đầu vào | Kết quả mong đợi (Expected Result) | Trạng thái |
| :--- | :--- | :--- | :--- | :--- | :--- | :---: |
| **TC-UI-01** | Khởi tạo trình duyệt ẩn danh (Anti-Bot Bypass) | Playwright Chromium sẵn sàng | Khởi tạo Chromium với cờ `--disable-blink-features=AutomationControlled` | Playwright BrowserContext | Thuộc tính `navigator.webdriver` trả về `undefined` (Bypass WAF bot flag) | **PASS** |
| **TC-UI-02** | Điều hướng và tìm kiếm Hashtag trên TikTok Web | Trang TikTok khả dụng | 1. Mở trang tìm kiếm hashtag<br>2. Chờ DOM load | URL `https://www.tiktok.com/tag/tintuc` | Phần tử danh sách video render thành công trong vòng 10 giây | **PASS** |
| **TC-UI-03** | Tự động hóa cuộn trang vô tận (Infinite Scroll) | Trang hashtag đã nạp | 1. Thực hiện cuộn xuống đáy trang<br>2. Chờ mạng tải thêm thẻ video | Script cuộn `window.scrollTo(0, document.body.scrollHeight)` kèm random delay | Số lượng phần tử video trong DOM tăng lên sau mỗi lần scroll | **PASS** |
| **TC-UI-04** | Trích xuất thuộc tính thẻ video từ DOM | Thẻ video đã xuất hiện | Quét danh sách phần tử `a[href*='/video/']` và lấy thuộc tính `href` | DOM Selector `div[data-e2e='challenge-item']` | Thu thập danh sách URL hợp lệ chứa ID video | **PASS** |
| **TC-UI-05** | Tự động chụp màn hình khi xảy ra lỗi (Screenshot on Failure) | Pytest Playwright fixture | Tạo tình huống assertion fail có chủ đích | Kiểm tra phần tử không tồn tại trong thời gian timeout | Hệ thống tự động lưu file ảnh chụp màn hình vào thư mục `logs/screenshots/` | **PASS** |

---

### NHÓM 5: RESILIENCE, CONCURRENCY & NON-FUNCTIONAL TESTING

| Test Case ID | Tên kịch bản | Điều kiện tiên quyết | Các bước thực hiện | Dữ liệu đầu vào | Kết quả mong đợi (Expected Result) | Trạng thái |
| :--- | :--- | :--- | :--- | :--- | :--- | :---: |
| **TC-RES-01** | Kiểm tra thuật toán Exponential Backoff kèm Jitter | Module downloader | Giả lập lỗi tải 3 lần liên tiếp và ghi nhận thời gian chờ | Lỗi mạng giả lập | Thời gian chờ tăng theo hàm mũ: $2^{attempt-1} + \text{jitter}$, không vượt quá `max_delay` (30s) | **PASS** |
| **TC-RES-02** | An toàn dữ liệu khi ghi đồng thời (Atomic Write Verification) | Module `json_storage` | Khởi chạy 10 threads cùng ghi vào 1 tệp JSON | 10 luồng ghi dữ liệu đồng thời | Tệp ghi ra qua tệp tạm `.part` rồi `replace()`, file JSON không bao giờ bị corrupt | **PASS** |
| **TC-RES-03** | Cơ chế khóa suy luận AI (Inference Lock) tránh tràn RAM | Mô hình AI Onnx nạp sẵn | Chạy 4 worker song song xử lý audio | 4 audio task đồng thời | Bước chạy AI được tuần tự hóa bằng `INFERENCE_LOCK`, RAM giữ mức an toàn < 3.5GB | **PASS** |
| **TC-RES-04** | Thu dọn tệp tạm tự động sau khi hoàn tất hoặc lỗi | Trình xử lý audio | Kiểm tra thư mục tạm trước và sau khi hoàn thành task | Tệp tạm `.part`, `.download_`, WAV trung gian | 100% tệp tạm được xóa sạch, không để rác trên ổ đĩa | **PASS** |
