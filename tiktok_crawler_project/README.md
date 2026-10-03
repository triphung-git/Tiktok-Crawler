# TikTok Crawler — Scrapy + Playwright

Pipeline crawl TikTok theo **hashtag** hoặc **username**, trả về danh sách URL video dưới dạng JSON.

## 1. Kiến trúc

```
tiktok_crawler_project/
├── scrapy.cfg
├── requirements.txt
├── output/                      # File JSON kết quả sẽ nằm ở đây
└── tiktok_crawler/
    ├── settings.py              # Cấu hình Scrapy + Playwright, rate limit
    ├── items.py                 # Định nghĩa schema dữ liệu (HashtagItem, UserItem)
    ├── pipelines.py             # Lọc trùng URL, xuất ra file .json
    └── spiders/
        ├── hashtag_spider.py    # Crawl theo hashtag: tiktok.com/tag/<tag>
        └── user_spider.py       # Crawl theo username: tiktok.com/@<username>
```

Vì sao dùng Playwright thay vì Scrapy thuần: TikTok render nội dung bằng JavaScript
(client-side rendering + infinite scroll), Scrapy request thuần chỉ lấy được HTML
"rỗng" ban đầu. `scrapy-playwright` cắm một trình duyệt headless (Chromium) vào làm
download handler, cho phép Scrapy điều khiển trang như người dùng thật (chờ selector,
cuộn trang) rồi mới lấy HTML đã render để parse.

## 2. Setup môi trường

```bash
# 1. Tạo virtualenv (khuyến nghị)
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# 2. Cài dependencies
pip install -r requirements.txt

# 3. Tải trình duyệt headless cho Playwright (bắt buộc, chỉ cần chạy 1 lần)
playwright install chromium
# Nếu thiếu thư viện hệ thống trên Linux:
playwright install-deps chromium
```

## 3. Chạy crawler

Crawl theo hashtag (nhiều hashtag cách nhau bằng dấu phẩy):

```bash
scrapy crawl hashtag -a tags="dance,comedy" -a max_scrolls=8
```

Crawl theo username:

```bash
scrapy crawl user -a usernames="username1,username2" -a max_scrolls=8
```

Tham số:
- `tags` / `usernames`: danh sách cách nhau bởi dấu phẩy, không cần `#` hay `@`.
- `max_scrolls`: số lần cuộn trang để load thêm video (mặc định 5). Cuộn càng
  nhiều thì lấy được càng nhiều video nhưng chạy càng lâu và dễ bị TikTok để ý.

Kết quả sẽ được `JsonExportPipeline` ghi vào `output/<spider_name>_<timestamp>.json`,
dạng:

```json
[
  {
    "hashtag": "dance",
    "video_url": "https://www.tiktok.com/@someuser/video/7123456789012345678",
    "author": "someuser",
    "scraped_at": "2026-09-14T10:00:00+00:00",
    "source_type": "hashtag"
  }
]
```

## 4. Cách trích xuất dữ liệu (2 lớp phòng hờ)

1. **CSS selector trên HTML đã render**: lấy toàn bộ thẻ `a[href*="/video/"]`
   sau khi trang đã load xong và đã cuộn.
2. **JSON state nhúng sẵn**: TikTok thường nhúng một khối dữ liệu JSON trong thẻ
   `<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__">`. `hashtag_spider.py` có hàm
   `_extract_from_embedded_json` để lấy thêm URL/author từ khối này — cách này bền
   hơn vì không phụ thuộc class CSS (TikTok đổi class thường xuyên), nhưng cấu trúc
   JSON có thể thay đổi theo thời gian nên cần kiểm tra lại định kỳ.

Muốn debug selector nhanh, dùng Playwright codegen để mở trình duyệt thật và xem
DOM trực tiếp:

```bash
playwright codegen https://www.tiktok.com/tag/dance
```

## 5. Các lưu ý vận hành quan trọng

- **Rate limit & AutoThrottle**: `settings.py` đã bật `AUTOTHROTTLE_ENABLED`,
  giới hạn `CONCURRENT_REQUESTS = 4` và delay ngẫu nhiên giữa các request. TikTok
  phát hiện traffic bất thường khá nhanh (chặn IP tạm thời hoặc yêu cầu xác thực/
  captcha). Nếu crawl ở quy mô lớn, cần thêm proxy pool (ưu tiên residential
  proxy) qua một download middleware riêng.
- **Đăng nhập / captcha**: các trang hashtag và profile công khai thường xem
  được không cần đăng nhập, nhưng TikTok có thể chèn màn hình xác minh khi nghi
  ngờ bot. Pipeline này không (và không nên) tự động vượt qua captcha — nếu gặp,
  nên giảm tốc độ crawl, đổi IP/User-Agent, hoặc tạm dừng.
- **Điều khoản dịch vụ (ToS)**: TikTok's Terms of Service giới hạn việc scraping
  tự động. Nên: chỉ thu thập dữ liệu công khai, không thu thập dữ liệu cá nhân
  nhạy cảm, giới hạn tần suất, và cân nhắc dùng
  [TikTok Research API](https://developers.tiktok.com/products/research-api/)
  hoặc [TikTok for Developers Display API](https://developers.tiktok.com/) nếu
  mục đích sử dụng phù hợp — đây là hướng đi tuân thủ và ổn định hơn về lâu dài
  so với scraping trực tiếp giao diện web.
- **Bảo trì selector**: TikTok thay đổi cấu trúc trang thường xuyên. Khi spider
  đột nhiên trả về 0 item, việc đầu tiên cần làm là mở trang bằng
  `playwright codegen` hoặc DevTools để kiểm tra lại selector/khối JSON.

## 6. Mở rộng thêm

- Thêm middleware xoay proxy/User-Agent trong `settings.py`
  (`DOWNLOADER_MIDDLEWARES`) nếu crawl ở quy mô lớn.
- Nếu muốn stream kết quả thay vì gom hết vào cuối, có thể dùng thêm
  `FEEDS` của Scrapy song song với pipeline hiện tại:
  ```python
  FEEDS = {
      "output/%(name)s_%(time)s.json": {"format": "json", "encoding": "utf-8"},
  }
  ```
- Có thể thêm spider thứ 3 để crawl theo **search keyword**
  (`tiktok.com/search?q=...`) theo cùng pattern với 2 spider hiện tại.
