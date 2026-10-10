# DEFECT REPORT: BUG-001

**Issue Key:** BUG-001  
**Project:** TikTok Speech Data Pipeline  
**Component:** Storage / Concurrency  
**Reporter:** Quality Engineer (QE)  
**Assignee:** Backend / Data Engineer  
**Status:** **RESOLVED & VERIFIED**  
**Resolution:** FIXED (Applied Atomic File Writing & Thread-Safe Lock)  

---

## 1. THÔNG TIN CHUNG (DEFECT SUMMARY)
- **Tiêu đề (Summary):** File JSON kết quả bị hỏng cấu trúc ("Unterminated string starting at line...") khi nhiều worker cùng ghi metadata đồng thời.
- **Mức độ nghiêm trọng (Severity):** **S1 - Critical** (Mất mát và sai lệch dữ liệu toàn bộ đợt chạy).
- **Mức độ ưu tiên (Priority):** **P1 - Blocker**.
- **Môi trường (Environment):** Windows 11, Python 3.10+, 4 Workers (`ThreadPoolExecutor`).

---

## 2. CÁC BƯỚC TÁI HIỆN LỖI (STEPS TO REPRODUCE)
1. Cấu hình pipeline chạy với 4 workers song song: `python scripts/run_pipeline.py --workers 4 --input data/processed/audio/WEEK1_0109/sources.json`.
2. Khi 2 worker hoàn thành việc phân đoạn âm thanh tại cùng một thời điểm (~miligiây), cả hai tiến trình đều cố gắng mở và ghi đè trực tiếp vào file `processed_index.json`:
   ```python
   # Đoạn code lỗi ban đầu:
   with open("processed_index.json", "w", encoding="utf-8") as f:
       json.dump(data, f, indent=2)
   ```
3. Giả lập ngắt đột ngột tiến trình hoặc tranh chấp file lock giữa các luồng.
4. Kiểm tra tệp `processed_index.json`.

---

## 3. KẾT QUẢ THỰC TẾ (ACTUAL RESULT)
- Tệp `processed_index.json` bị cụt nội dung ở giữa chừng, kích thước file giảm đột ngột về 0 byte hoặc chứa chuỗi JSON dang dở.
- Lần chạy tiếp theo của pipeline bị crash hoàn toàn với lỗi:
  ```text
  json.decoder.JSONDecodeError: Unterminated string starting at line 124 column 5 (char 3820)
  ```

---

## 4. KẾT QUẢ MONG ĐỢI (EXPECTED RESULT)
- Hệ thống phải đảm bảo tính toàn vẹn (ACID / Data Consistency). Dữ liệu ghi ra file phải nguyên tử (Atomic): hoặc ghi thành công trọn vẹn, hoặc giữ nguyên trạng thái cũ, tuyệt đối không được sinh ra file bị hỏng một phần.

---

## 5. PHÂN TÍCH NGUYÊN NHÂN GỐC RỄ (ROOT CAUSE ANALYSIS)
- Việc mở file bằng cờ `"w"` sẽ truncate (xóa sạch) nội dung file về 0 byte trước khi bắt đầu ghi nội dung mới.
- Trong môi trường đa luồng không có khóa (Mutex Lock), hai luồng ghi đan xen các khối dữ liệu vào cùng một file descriptor.
- Hệ điều hành Windows khóa truy cập file độc quyền, dẫn đến lỗi PermissionError hoặc tệp ghi dở dang nếu một luồng bị ngắt.

---

## 6. GIẢI PHÁP ĐÃ TRIỂN KHAI & XÁC MINH (FIX & VERIFICATION)
1. **Triển khai cơ chế Atomic Write tầng OS:**
   - Tạo file tạm `.part`: `temp_path = file_path.with_suffix(".part")`.
   - Ghi dữ liệu đầy đủ và thực hiện flush xuống đĩa cứng: `f.flush(); os.fsync(f.fileno())`.
   - Thực hiện hoán đổi nguyên tử: `os.replace(temp_path, file_path)`.
2. **Triển khai Thread-safe Lock:**
   - Bao bọc toàn bộ thao tác ghi bằng `threading.Lock()` trong lớp `MetadataManager`.
3. **Kết quả kiểm thử lại (Retest Result):**
   - Chạy test case `tests/test_storage.py::test_atomic_write_and_load_json` với 10 threads đồng thời: **PASSED (100% tệp hợp lệ)**.
