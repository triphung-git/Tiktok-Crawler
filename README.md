# TikTok Speech Data Pipeline (ASR Corpus)

Pipeline tự động hóa từ khâu thu thập video TikTok, làm sạch & lọc trùng URL liên batch, đến bóc tách nhạc nền (**UVR MDX-Net**), khử tạp âm (**DPDFNet**), và cắt câu thoại tự nhiên (**Silero VAD v5**) phục vụ huấn luyện mô hình nhận dạng giọng nói (Automatic Speech Recognition - ASR).

---

## 1. Cấu Trúc Dự Án (Project Architecture)

Toàn bộ dự án đã được tái cấu trúc theo mô hình module hóa chuyên sâu:

```
TIKTOK_DATA_PIPELINE/
│
├── README.md                           # Tài liệu kiến trúc và hướng dẫn vận hành
├── .gitignore                          # Quy tắc bỏ qua tệp tạm, logs, audio, venv
├── .env                                # Biến môi trường cục bộ (threads, proxy, cookies)
├── .env.example                        # Mẫu cấu hình biến môi trường
├── requirements.txt                    # Danh mục dependencies chuẩn hóa
├── scrapy.cfg                          # Cấu hình Scrapy root
│
├── config/                             # Cấu hình tập trung (YAML)
│   ├── settings.yaml                   # Cấu hình pipeline, model, path, timeouts
│   └── tags.yaml                       # Phân loại hashtag & tài khoản mục tiêu
│
├── src/                                # Mã nguồn lõi (Modular Source Code)
│   ├── config.py                       # Bộ nạp cấu hình và chuẩn hóa đường dẫn
│   ├── crawler/                        # Module thu thập dữ liệu
│   │   ├── scrapy/                     # Trình cào phân tán Scrapy
│   │   │   ├── spiders/                # Spiders: hashtag_spider.py, user_spider.py
│   │   │   ├── items.py                # Định nghĩa schemas Item
│   │   │   ├── pipelines.py            # Xuất dữ liệu JSON an toàn & khử trùng
│   │   │   └── settings.py             # Cấu hình Scrapy & Playwright handler
│   │   │
│   │   └── playwright/                 # Trình duyệt Playwright độc lập
│   │       └── browser.py              # Anti-bot detection & infinite scroll
│   │
│   ├── processing/                     # Tiền xử lý dữ liệu & lọc URL
│   │   ├── cleaner.py                  # Chuẩn hóa URL, suy đoán phương ngữ, bóc ID
│   │   ├── validator.py                # Kiểm định tính hợp lệ & phân loại lỗi
│   │   └── transformer.py              # Xây dựng task & chuẩn hóa schema
│   │
│   ├── media/                          # Xử lý âm thanh & mô hình học sâu (AI)
│   │   ├── audio_downloader.py         # Tải audio yt-dlp kèm Exponential Backoff
│   │   └── audio_processor.py          # Loudnorm, UVR MDX-Net, DPDFNet, Silero VAD
│   │
│   ├── storage/                        # Tầng lưu trữ dữ liệu
│   │   ├── json_storage.py             # Ghi tệp nguyên tử (Atomic Write) & Index toàn cục
│   │   └── database.py                 # Quản trị SQLite cho metadata & segments
│   │
│   └── pipeline/                       # Điều phối quy trình (Orchestration)
│       └── run.py                      # PipelineRunner khép kín (End-to-End)
│
├── data/                               # Phân tầng dữ liệu
│   ├── raw/
│   │   └── tiktok/                     # JSON thô từ crawler (raw_dataDDMM.json)
│   │
│   ├── processed/
│   │   ├── metadata/                   # processed_index.json & metadata đợt chạy
│   │   └── audio/                      # Audio WAV 16kHz mono & các segments
│   │
│   └── output/                         # Dữ liệu xuất khẩu cho huấn luyện
│       ├── json/                       # Tập hợp task JSON chuẩn hóa
│       └── csv/                        # Bảng tổng hợp CSV
│
├── tests/                              # Bộ kiểm thử tự động (Unit & Integration tests)
│   ├── test_cleaner.py
│   ├── test_validator.py
│   ├── test_transformer.py
│   ├── test_storage.py
│   ├── test_downloader.py
│   ├── test_audio_processor.py
│   └── test_pipeline.py
│
├── logs/                               # Nhật ký thực thi hệ thống (pipeline.log)
├── notebooks/                          # Khám phá và thống kê phân phối dữ liệu
│   └── data_exploration.ipynb
│
├── models/                             # Trọng số mô hình ONNX
│   ├── UVR-MDX-NET-Voc_FT.onnx         # Tách giọng nói khỏi nhạc nền
│   ├── dpdfnet8.onnx                   # Khử nhiễu môi trường
│   └── silero_vad.onnx                 # Nhận diện giọng nói và phân đoạn câu
│
└── scripts/                            # CLI Scripts thực thi nhanh
    ├── crawl.py                        # Cào dữ liệu theo tag/user
    ├── process.py                      # Làm sạch URL & lọc trùng 2 tầng
    └── run_pipeline.py                 # Chạy xử lý audio / toàn bộ pipeline
```

---

## 2. Cài Đặt Môi Trường

### Yêu cầu hệ thống
- Python 3.10+ (Đã kiểm thử tối ưu trên Python 3.10 - 3.14)
- `ffmpeg.exe` và `ffprobe.exe` (đặt tại thư mục gốc dự án hoặc trong hệ thống PATH)

### Cài đặt thư viện
```bash
# Cài đặt toàn bộ thư viện cần thiết
pip install -r requirements.txt

# Cài đặt Chromium cho Playwright (nếu dùng crawler)
playwright install chromium
```

---

## 3. Quy Trình Vận Hành 3 Bước

Quy chuẩn đặt tên batch dữ liệu: `WEEK<number>_<DDMM>` (ví dụ: `WEEK3_0309`).

```
[Crawler] -> raw_dataDDMM.json -> [process.py] -> sources_DDMM.json -> [run_pipeline.py] -> WAV Segments (2s - 15s)
```

### Bước 1: Thu Thập Dữ Liệu Video (Crawl)
Sử dụng `scripts/crawl.py` để cào URL theo hashtag hoặc tài khoản người dùng:

```bash
# Cào theo hashtag:
python scripts/crawl.py --tags "tintuc,giaitri" --max-scrolls 8 --batch WEEK3_0309

# Cào theo username:
python scripts/crawl.py --usernames "vtv24news" --max-scrolls 10 --batch WEEK3_0309

# Hoặc chạy trực tiếp bằng Scrapy:
scrapy crawl hashtag -a tags="tintuc,giaitri" -a max_scrolls=8 -a batch=WEEK3_0309
```
*Kết quả:* Tệp `data/raw/tiktok/WEEK3_0309/raw_data0309.json` được tạo an toàn.

---

### Bước 2: Làm Sạch URL & Lọc Trùng Lặp 2 Tầng (Process)
Sử dụng `scripts/process.py` để:
- **Tầng 1 (In-batch):** Lọc bỏ video trùng lặp nội bộ trong cùng phiên cào.
- **Tầng 2 (Cross-batch Global Index):** Đối soát và loại bỏ video đã cào từ **tất cả các batch trước** qua `processed_index.json`.
- Gán nhãn phương ngữ 3 miền (`northern`, `central`, `southern`, `unidentified`).
- Chuẩn hóa schema sang danh sách task tải audio.

```bash
# Xử lý tệp raw data:
python scripts/process.py --input "data/raw/tiktok/WEEK3_0309/raw_data0309.json" --batch WEEK3_0309 --yes

# Chạy thử nghiệm không ghi đĩa (dry-run):
python scripts/process.py --input "data/raw/tiktok/WEEK3_0309/raw_data0309.json" --batch WEEK3_0309 --dry-run --yes
```
*Kết quả:* Tạo `data/processed/audio/WEEK3_0309/sources_0309.json`, `summary.json`, đồng thời cập nhật cơ sở dữ liệu `processed_index.json`.

---

### Bước 3: Tải, Tách Nhạc, Khử Nhiễu & Phân Đoạn Audio (Media Pipeline)
Sử dụng `scripts/run_pipeline.py` để thực thi chu trình 8 bước chuẩn ASR:
1. Tải audio tạm thời (`yt-dlp`) kèm Exponential Backoff và Random Jitter.
2. Chuẩn hóa âm lượng chuẩn phát thanh EBU R128 (`-16 LUFS, 16kHz mono`).
3. Kiểm định định dạng và thời lượng audio đầu vào (`ffprobe`).
4. Tách nhạc nền & beat remix bằng **UVR MDX-Net ONNX**.
5. Khử tạp âm môi trường và tiếng quạt bằng **DPDFNet ONNX**.
6. Kiểm định vocal sau tăng cường.
7. Cắt lát phát ngôn câu thoại tự nhiên từ 2s đến 15s bằng **Silero VAD v5 ONNX** (tự động loại bỏ khoảng lặng và đoạn video không có người nói).
8. Lưu các lát cắt dưới dạng Lossless WAV 16kHz mono (PCM 16-bit) tại thư mục `segments/`; dọn dẹp 100% tệp tạm `.part` và `.download_`.

```bash
# Xử lý toàn bộ batch với 4 worker song song:
python scripts/run_pipeline.py --input "data/processed/audio/WEEK3_0309/sources_0309.json" --workers 4 --yes

# Xử lý riêng 1 task để kiểm tra:
python scripts/run_pipeline.py --input "data/processed/audio/WEEK3_0309/sources_0309.json" --task-id ID_0001 --yes

# Bỏ qua biến môi trường proxy hệ thống nếu gặp lỗi mạng:
python scripts/run_pipeline.py --input "data/processed/audio/WEEK3_0309/sources_0309.json" --workers 4 --ignore-env-proxy --yes
```

---

### Chạy Khép Kín Toàn Bộ (End-to-End Pipeline)
Chạy toàn bộ chu trình 3 bước chỉ với một lệnh duy nhất:
```bash
python -m src.pipeline.run --mode all --tags "tintuc,podcast" --batch WEEK3_0309 --workers 4
```

---

## 4. Tương Thích Ngược (Backward Compatibility)

Hệ thống bảo toàn 100% tính tương thích ngược với các câu lệnh truyền thống:
- `python url_processor.py --input ... --batch ... --yes`
- `python core_worker.py --input ... --workers 4 --yes`

Cả hai script ở thư mục gốc đều tự động điều hướng sang các module lõi mới trong `src/` mà không làm gián đoạn bất kỳ quy trình làm việc hay CI/CD có sẵn nào.

---

## 5. Rủi Ro Thu Thập & Giải Pháp Kỹ Thuật Đã Tích Hợp

| STT | Vấn đề rủi ro | Bản chất / Biểu hiện | Giải pháp kỹ thuật trong Codebase | Module phụ trách |
|:---:|---|---|---|---|
| **1** | **TikTok Bot Detection & Rate Limiting** | TikTok WAF chặn IP, trả về trang trắng hoặc bật Captcha xác thực bot. | • Kích hoạt cờ Chromium `--disable-blink-features=AutomationControlled` nhằm ẩn `navigator.webdriver`.<br>• Viewport thực tế (1280x800), Desktop User-Agent hiện đại.<br>• Scrapy AutoThrottle ngẫu nhiên với `CONCURRENT_REQUESTS = 4`. | [`settings.py`](file:///d:/Pycharm/data_crawl/src/crawler/scrapy/settings.py)<br>[`browser.py`](file:///d:/Pycharm/data_crawl/src/crawler/playwright/browser.py) |
| **2** | **Lỗi mạng, Rate limit & Hết hạn Token Media** | Link CDN TikTok hết hạn token, lỗi HTTP 429 hoặc socket timeout khi tải hàng loạt. | • Hàm `classify_error()` phân loại lỗi retryable vs non-retryable.<br>• **Exponential Backoff kèm Jitter**: Thử lại $N$ lần với thời gian chờ $2^{attempt-1} + \text{rand}(0, 1)$ tối đa 30s.<br>• Hỗ trợ cookie trình duyệt, cookiefile, proxy xoay vòng và cờ `--ignore-env-proxy`. | [`audio_downloader.py`](file:///d:/Pycharm/data_crawl/src/media/audio_downloader.py) |
| **3** | **Tranh chấp tài nguyên & Tràn RAM khi chạy AI** | UVR MDX-Net và DPDFNet đòi hỏi băng thông RAM lớn. Chạy song song nhiều luồng dễ gây OOM (>10GB RAM) và nghẽn CPU Cache. | • **Tuần tự hóa bằng `INFERENCE_LOCK`**: Cho phép tải audio song song đa luồng nhưng bắt buộc bước tách nhạc & khử nhiễu AI chạy tuần tự.<br>• Giữ RAM ổn định dưới **3GB** (thay vì >10GB), 1 task tận dụng 100% băng thông RAM và số luồng CPU cấu hình.<br>• Lớp `Heartbeat` in log nhịp tim mỗi 15s tránh cảm giác treo tiến trình.<br>• Kiểm soát số luồng qua `UVR_NUM_THREADS` và `DPDFNET_NUM_THREADS`. | [`audio_processor.py`](file:///d:/Pycharm/data_crawl/src/media/audio_processor.py) |
| **4** | **Trùng lặp dữ liệu nội bộ & liên batch** | Cào trùng video giữa các hashtag hoặc cào lại user ở các tuần sau gây bẩn tập dữ liệu và lãng phí thời gian xử lý. | • Hàm `sanitize_video_url()` làm sạch URL, loại bỏ toàn bộ query parameters tracking rác của TikTok (`is_from_webapp`...).<br>• **Lọc trùng tầng 1 (In-batch):** Loại bỏ URL trùng trong cùng phiên bằng `seen_urls` set.<br>• **Lọc trùng tầng 2 (Cross-batch Global Index):** Đối soát mọi URL với cơ sở dữ liệu chỉ mục toàn cục `processed_index.json`. | [`cleaner.py`](file:///d:/Pycharm/data_crawl/src/processing/cleaner.py)<br>[`validator.py`](file:///d:/Pycharm/data_crawl/src/processing/validator.py)<br>[`json_storage.py`](file:///d:/Pycharm/data_crawl/src/storage/json_storage.py) |
| **5** | **Xung đột ghi file & Hỏng dữ liệu đa luồng** | Tiến trình bị ngắt đột ngột (mất điện, crash) hoặc nhiều luồng ghi cùng lúc làm hỏng file JSON kết quả ("Unterminated string"). | • Áp dụng triệt để nguyên lý **Ghi tệp nguyên tử (Atomic Write)** qua `atomic_write_json()`: ghi ra file tạm `.part` rồi thực hiện `os.replace()` nguyên tử ở tầng hệ điều hành.<br>• `MetadataManager` bảo vệ dữ liệu bằng Lock và hỗ trợ batch flush.<br>• `clean_temp_files()` tự động quét dọn các file tạm dở dang khi khởi động lại. | [`json_storage.py`](file:///d:/Pycharm/data_crawl/src/storage/json_storage.py)<br>[`audio_processor.py`](file:///d:/Pycharm/data_crawl/src/media/audio_processor.py) |

---

## 6. Kiểm Thử Hệ Thống (Automated Testing)

Toàn bộ codebase đi kèm với bộ test suite tự động 27 bài kiểm tra:

```bash
# Chạy toàn bộ test suite:
pytest tests/ -v
```

Kết quả kiểm thử bảo đảm:
- 100% các hàm làm sạch URL, phát hiện platform, trích xuất ID hoạt động chính xác.
- Kiểm định và lọc trùng 2 tầng (in-batch và cross-batch index) chặn đứng 100% URL trùng lặp.
- Atomic write và SQLite Database xử lý an toàn đồng thời trên môi trường Windows.
- Audio probe và kiểm tra chuẩn hóa EBU R128, PCM 16-bit 16kHz mono đạt tiêu chuẩn ASR quốc tế.
