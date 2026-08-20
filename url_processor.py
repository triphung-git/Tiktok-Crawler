import json
import os
import re
import unicodedata
from datetime import datetime, timezone


def sanitize_tiktok_url(raw_url: str) -> str:
    """
    Làm sạch URL: Xóa bỏ các tham số tracking phía sau dấu '?'.
    """
    if not raw_url or not isinstance(raw_url, str):
        return None

    clean_url = raw_url.split('?')[0].strip()

    # Đảm bảo URL thuộc về nền tảng TikTok
    if "tiktok.com" in clean_url:
        return clean_url
    return None


def format_duration(duration_seconds):
    """Chuyển thời lượng tính bằng giây sang định dạng HH:MM:SS hoặc MM:SS."""
    if duration_seconds is None:
        return None

    try:
        total_seconds = int(duration_seconds)
    except (TypeError, ValueError):
        return None

    if total_seconds < 0:
        return None

    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


REGIONAL_MARKERS = {
    "northen": {
        "bo", "me", "qua", "ngo", "lac", "thia", "coc", "dua", "bao"
    },
    "central": {
        "mo", "te", "rang", "rua", "ni", "no", "ri", "tau", "mi", "chi", "man"
    },
    "southern": {
        "ma", "ba", "trai", "bap", "dau phong", "muong", "ly", "thom", "hong", "nghen"
    }
}


def infer_regional_dialect(text: str):
    """Suy đoán vùng miền từ caption theo bộ giá trị language_region."""
    if not isinstance(text, str) or not text.strip():
        return "northen"

    normalized_text = unicodedata.normalize("NFD", text.lower())
    normalized_text = "".join(
        character for character in normalized_text
        if unicodedata.category(character) != "Mn"
    )
    normalized_text = re.sub(r"[^a-z0-9\s]", " ", normalized_text)
    words = set(normalized_text.split())
    scores = {
        region: sum(
            1 for marker in markers
            if (" " in marker and marker in normalized_text) or marker in words
        )
        for region, markers in REGIONAL_MARKERS.items()
    }

    best_region = max(scores, key=scores.get)
    best_score = scores[best_region]
    if best_score == 0:
        return "northen"
    if list(scores.values()).count(best_score) > 1:
        return "mixed"

    return best_region


def extract_video_id(url: str, item: dict) -> str:
    """Lấy video ID từ metadata hoặc URL TikTok."""
    video_id = item.get("id")
    if video_id:
        return str(video_id)

    match = re.search(r"/video/(\d+)", url or "")
    return match.group(1) if match else ""


def process_and_export_urls(input_file: str, output_file: str):
    """
    Đọc JSON thô, xử lý URL và xuất ra định dạng Task tiêu chuẩn.
    """
    if not os.path.exists(input_file):
        print(f"[-] Lỗi: Không tìm thấy file đầu vào '{input_file}'")
        return

    print(f"[*] Đang đọc dữ liệu từ '{input_file}'...")
    with open(input_file, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            print("[-] Lỗi: Cấu trúc file JSON đầu vào không hợp lệ.")
            return

    tasks = []
    seen_urls = set()
    crawl_batch = os.getenv("CRAWL_BATCH", "tt_batch_01")
    crawled_at = datetime.now(timezone.utc).isoformat()

    for item in data:
        # Trích xuất URL từ key 'webVideoUrl'
        raw_url = item.get("webVideoUrl", "")
        clean_url = sanitize_tiktok_url(raw_url)

        # Lọc trùng lặp và đóng gói
        if clean_url and clean_url not in seen_urls:
            seen_urls.add(clean_url)

            video_meta = item.get("videoMeta") or {}
            duration_seconds = video_meta.get("duration")
            text_language = item.get("textLanguage") or "unknown"
            language_region = infer_regional_dialect(item.get("text", ""))
            platform_video_id = extract_video_id(clean_url, item)
            subtitle_links = video_meta.get("subtitleLinks") or []

            tasks.append({
                "task_id": f"ID_{len(tasks) + 1:04d}",
                "item_id": f"tt_{platform_video_id}",
                "platform": "tiktok",
                "platform_video_id": platform_video_id,
                "original_url": clean_url,
                "title": item.get("text", ""),
                "description": item.get("text", ""),
                "posted_at": item.get("createTimeISO"),
                "duration_seconds": duration_seconds,
                "duration_formatted": format_duration(duration_seconds),
                "text_language": text_language,
                "language_raw": text_language,
                "language_region": language_region,
                "crawl_batch": crawl_batch,
                "crawled_at": crawled_at,
                "platform_meta": {
                    "music_is_original": bool((item.get("musicMeta") or {}).get("musicOriginal", False)),
                    "is_duet": bool(item.get("isDuet", False)),
                    "is_stitch": bool(item.get("isStitch", False)),
                    "has_platform_captions": bool(subtitle_links)
                }
            })

    # Ghi dữ liệu sạch ra file nguồn mới (sources.json)
    print(f"[*] Đang xuất dữ liệu ra file '{output_file}'...")
    with open(output_file, 'w', encoding='utf-8') as f:
        # ensure_ascii=False giúp giữ nguyên ký tự tiếng Việt (nếu có sau này)
        # indent=4 giúp file JSON dễ đọc với con người
        json.dump(tasks, f, ensure_ascii=False, indent=4)

    print(f"[+] Thành công! Từ {len(data)} records gốc, đã lọc và xuất {len(tasks)} URLs sạch.")


# ================= HƯỚNG DẪN SỬ DỤNG =================
if __name__ == "__main__":
    # Thay đổi tên file này thành tên file JSON chứa 300 URLs của bạn
    INPUT_JSON_FILE = "raw_data.json"

    # Tên file đầu ra mà Worker sẽ đọc
    OUTPUT_JSON_FILE = "sources.json"

    process_and_export_urls(INPUT_JSON_FILE, OUTPUT_JSON_FILE)