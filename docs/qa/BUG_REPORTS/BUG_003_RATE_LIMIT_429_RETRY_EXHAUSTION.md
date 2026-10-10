# DEFECT REPORT: BUG-003

**Issue Key:** BUG-003  
**Project:** TikTok Speech Data Pipeline  
**Component:** Media / Downloader  
**Reporter:** Quality Engineer (QE)  
**Assignee:** Core Engineer  
**Status:** **RESOLVED & VERIFIED**  
**Resolution:** FIXED (Exponential Backoff with Full Jitter & Max Delay Cap)  

---

## 1. THÔNG TIN CHUNG (DEFECT SUMMARY)
- **Tiêu đề (Summary):** Trình tải audio bị sập ngay lập tức hoặc gửi bão request (Retry Storm) khi TikTok CDN phản hồi HTTP 429 Too Many Requests.
- **Mức độ nghiêm trọng (Severity):** **S2 - Major** (Làm mất tác vụ tải, nguy cơ bị ban IP dài hạn).
- **Mức độ ưu tiên (Priority):** **P2 - High**.
- **Môi trường (Environment):** Python 3.10+, `yt-dlp`, `curl-cffi`.

---

## 2. CÁC BƯỚC TÁI HIỆN LỖI (STEPS TO REPRODUCE)
1. Chạy tiến trình tải 20 video liên tục trong thời gian ngắn mà không có khoảng nghỉ.
2. TikTok CDN phát hiện lưu lượng bất thường và trả về:
   ```text
   HTTP Error 429: Too Many Requests
   ```
3. Khảo sát hành vi của vòng lặp retry ban đầu:
   - Thử lại ngay lập tức không có delay (`delay = 0`).
   - Sau đó tiếp tục thất bại và văng ngoại lệ `DownloadError` ra ngoài khiến worker dừng hẳn.

---

## 3. KẾT QUẢ THỰC TẾ (ACTUAL RESULT)
- Toàn bộ các request tiếp theo tiếp tục bị CDN chặn với lỗi 429.
- Hiện tượng "Thundering Herd / Retry Storm": nhiều thread cùng thử lại tại cùng một thời điểm làm tăng áp lực lên CDN và dẫn đến IP bị khóa tạm thời 15 phút.

---

## 4. KẾT QUẢ MONG ĐỢI (EXPECTED RESULT)
- Hệ thống cần phân biệt giữa lỗi có thể thử lại (**Retryable Errors**: HTTP 429, Socket Timeout, 503) và lỗi không thể thử lại (**Non-retryable Errors**: Video Removed, 404, Format Not Found).
- Đối với lỗi 429, thời gian chờ phải tăng theo hàm mũ (Exponential Backoff) cộng thêm độ trễ ngẫu nhiên (Random Jitter) để tránh bão request đồng bộ.

---

## 5. PHÂN TÍCH NGUYÊN NHÂN GỐC RỄ (ROOT CAUSE ANALYSIS)
- Thiếu hàm phân loại lỗi `classify_error()` trước khi quyết định thử lại.
- Cơ chế tính thời gian chờ chưa áp dụng thuật toán lùi lũy thừa chuẩn công nghiệp:
  $$\text{Delay} = \min(\text{MaxDelay}, \text{BaseDelay} \times 2^{\text{attempt}-1} + \text{rand}(0, 1))$$

---

## 6. GIẢI PHÁP ĐÃ TRIỂN KHAI & XÁC MINH (FIX & VERIFICATION)
1. **Thêm hàm phân loại lỗi chuyên biệt:**
   - Trong `src/processing/validator.py`: `classify_error(error_str) -> "rate_limit" | "network_error" | "not_found"`.
2. **Cài đặt thuật toán Exponential Backoff kèm Jitter:**
   - Trong `src/media/audio_downloader.py`:
     ```python
     delay = min(self.max_delay, (self.base_delay * (2 ** (attempt - 1))) + random.uniform(0.1, 1.0))
     time.sleep(delay)
     ```
3. **Kết quả kiểm thử lại (Retest Result):**
   - Chạy test case `tests/test_downloader.py::test_error_classification_for_retries`: **PASSED**.
   - Chạy mô phỏng kiểm thử tự động tại `tests/api/test_pipeline_api.py::test_http_429_retry_resilience`: **PASSED**.
