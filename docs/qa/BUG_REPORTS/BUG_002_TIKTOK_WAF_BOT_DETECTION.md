# DEFECT REPORT: BUG-002

**Issue Key:** BUG-002  
**Project:** TikTok Speech Data Pipeline  
**Component:** Crawler / Playwright  
**Reporter:** Quality Engineer (QE)  
**Assignee:** Crawler Engineer  
**Status:** **RESOLVED & VERIFIED**  
**Resolution:** FIXED (Applied Anti-bot evasion flags & Dynamic Human Delay)  

---

## 1. THÔNG TIN CHUNG (DEFECT SUMMARY)
- **Tiêu đề (Summary):** TikTok WAF kích hoạt Captcha Challenge và chặn IP khi khởi tạo Playwright ở chế độ Headless mặc định.
- **Mức độ nghiêm trọng (Severity):** **S1 - Critical** (Không thể thu thập dữ liệu video, crawler bị dừng ngay vòng lặp đầu tiên).
- **Mức độ ưu tiên (Priority):** **P1 - Blocker**.
- **Môi trường (Environment):** Playwright Chromium 1.43+, Windows 11.

---

## 2. CÁC BƯỚC TÁI HIỆN LỖI (STEPS TO REPRODUCE)
1. Khởi tạo Playwright context mặc định:
   ```python
   browser = await playwright.chromium.launch(headless=True)
   page = await browser.new_page()
   await page.goto("https://www.tiktok.com/tag/tintuc")
   ```
2. Thực hiện cuộn trang liên tục 5 lần với tốc độ cố định `page.evaluate("window.scrollTo(0, document.body.scrollHeight)")`.
3. Kiểm tra DOM trả về.

---

## 3. KẾT QUẢ THỰC TẾ (ACTUAL RESULT)
- Trang web chuyển hướng sang màn hình xác thực: `https://www.tiktok.com/verify-center?...`
- Modal xác thực Captcha trượt xuất hiện, che toàn bộ danh sách thẻ video.
- Thuộc tính JavaScript trong trang: `navigator.webdriver == true` bị hệ thống chống bot của TikTok phát hiện.
- Crawler trả về 0 kết quả URL video.

---

## 4. KẾT QUẢ MONG ĐỢI (EXPECTED RESULT)
- Trình duyệt mô phỏng chính xác hành vi người dùng thật (Real User Emulation).
- WAF không kích hoạt Captcha; danh sách thẻ video `div[data-e2e='challenge-item']` tải liên tục khi cuộn trang.

---

## 5. PHÂN TÍCH NGUYÊN NHÂN GỐC RỄ (ROOT CAUSE ANALYSIS)
- Playwright Chromium mặc định kích hoạt biến nội bộ `window.navigator.webdriver = true`.
- Các request gửi đi thiếu User-Agent thực tế của trình duyệt Desktop hiện đại (Chrome 120+).
- Tốc độ cuộn trang đều đặn 0ms độ trễ (không có jitter/ngẫu nhiên) là dấu hiệu nhận diện bot tự động điển hình của hệ thống WAF.

---

## 6. GIẢI PHÁP ĐÃ TRIỂN KHAI & XÁC MINH (FIX & VERIFICATION)
1. **Loại bỏ cờ tự động hóa của Chromium:**
   - Cấu hình tham số khởi chạy: `args=["--disable-blink-features=AutomationControlled"]`.
2. **Cấu hình Viewport & User-Agent thật:**
   - Cài đặt `viewport={"width": 1280, "height": 800}`.
   - Sử dụng Desktop User-Agent: `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36...`.
3. **Mô phỏng hành vi người dùng (Humanized Scrolling):**
   - Thêm thời gian chờ ngẫu nhiên giữa các lần cuộn: `random.uniform(1.8, 3.5)`.
4. **Kết quả kiểm thử lại (Retest Result):**
   - Chạy kiểm thử tự động `tests/ui/test_tiktok_ui.py::test_playwright_anti_bot_detection`: **PASSED**.
   - `navigator.webdriver` trả về `undefined`. Tỷ lệ thu thập thành công 50+ video liên tục không bị chặn.
