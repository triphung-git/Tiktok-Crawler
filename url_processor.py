import json
import os
import re
import unicodedata
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse


SUPPORTED_DOMAINS = {
    "tiktok.com": "tiktok",
    "youtube.com": "youtube",
    "youtu.be": "youtube",
    "facebook.com": "facebook",
    "fb.watch": "facebook",
}


def detect_platform(raw_url: str) -> Optional[str]:
    """Nhận diện nền tảng từ hostname, không chấp nhận domain giả mạo."""
    if not isinstance(raw_url, str) or not raw_url.strip():
        return None

    hostname = (urlparse(raw_url.strip()).hostname or "").lower().removeprefix("www.")
    for domain, platform in SUPPORTED_DOMAINS.items():
        if hostname == domain or hostname.endswith(f".{domain}"):
            return platform
    return None


def sanitize_video_url(raw_url: str) -> Optional[str]:
    """Làm sạch URL, giữ query `v` cần thiết của YouTube."""
    platform = detect_platform(raw_url)
    if not platform:
        return None

    parsed_url = urlparse(raw_url.strip())
    query = parse_qs(parsed_url.query)
    path = parsed_url.path.rstrip("/") or "/"

    if platform in {"youtube", "facebook"} and query.get("v"):
        domain = "www.youtube.com" if platform == "youtube" else "www.facebook.com"
        return f"https://{domain}/watch?v={query['v'][0]}"
    return f"https://{parsed_url.netloc.lower()}{path}"


sanitize_tiktok_url = sanitize_video_url


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


def extract_video_id(url: str, item: dict, platform: str) -> str:
    """Lấy video ID từ metadata hoặc URL theo từng nền tảng."""
    video_id = item.get("id")
    if video_id:
        return str(video_id)

    parsed_url = urlparse(url or "")
    query = parse_qs(parsed_url.query)
    if platform in {"youtube", "facebook"} and query.get("v"):
        return query["v"][0]
    if platform == "youtube" and parsed_url.netloc.endswith("youtu.be"):
        return parsed_url.path.strip("/").split("/")[0]

    patterns = {
        "tiktok": (r"/video/(\d+)",),
        "youtube": (r"/shorts/([^/?]+)", r"/embed/([^/?]+)"),
        "facebook": (r"/(?:videos|reel|reels)/([^/?]+)",),
    }
    for pattern in patterns.get(platform, ()):
        match = re.search(pattern, parsed_url.path)
        if match:
            return match.group(1)
    return ""


def next_output_path(directory: Path, date_token: str) -> Path:
    """Tạo tên output không ghi đè file của cùng ngày."""
    base = directory / f"sources_{date_token}.json"
    if not base.exists():
        return base
    suffix = 1
    while True:
        candidate = directory / f"sources_{date_token}_{suffix:02d}.json"
        if not candidate.exists():
            return candidate
        suffix += 1


def find_input_file(directory: Path) -> tuple[Path, str]:
    candidates = sorted(directory.glob("raw_data[0-9][0-9][0-9][0-9].json"))
    if not candidates:
        raise FileNotFoundError(
            f"Không tìm thấy file raw_dataDDMM.json trong thư mục: {directory}"
        )
    if len(candidates) > 1:
        print("Các file input tìm thấy:")
        for index, candidate in enumerate(candidates, start=1):
            print(f"  {index}. {candidate.name}")
        choice = input("Chọn số file input: ").strip()
        if not choice.isdigit() or not 1 <= int(choice) <= len(candidates):
            raise ValueError("Lựa chọn file input không hợp lệ.")
        selected = candidates[int(choice) - 1]
    else:
        selected = candidates[0]
    date_token = re.fullmatch(r"raw_data(\d{4})\.json", selected.name).group(1)
    return selected, date_token


def confirm_input(input_file: Path, record_count: int) -> None:
    print(f"\nInput được chọn: {input_file}")
    print(f"Số records: {record_count}")
    answer = input("Xác nhận xử lý file này? [y/N]: ").strip().lower()
    if answer not in {"y", "yes"}:
        raise RuntimeError("Đã hủy xử lý theo xác nhận của người dùng.")

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
        if not isinstance(item, dict):
            continue
        # Trích xuất URL từ key 'webVideoUrl'
        raw_url = item.get("webVideoUrl", "")
        platform = detect_platform(raw_url)
        clean_url = sanitize_video_url(raw_url)

        # Lọc trùng lặp và đóng gói
        if clean_url and clean_url not in seen_urls:
            seen_urls.add(clean_url)

            video_meta = item.get("videoMeta") or {}
            duration_seconds = item.get("videoMeta.duration", video_meta.get("duration"))
            text_language = item.get("textLanguage") or "unknown"
            language_region = infer_regional_dialect(item.get("text", ""))
            platform_video_id = extract_video_id(clean_url, item, platform)
            subtitle_links = item.get("videoMeta.subtitleLinks", video_meta.get("subtitleLinks")) or []
            platform_prefix = {"tiktok": "tt", "youtube": "yt", "facebook": "fb"}[platform]

            tasks.append({
                "task_id": f"ID_{len(tasks) + 1:04d}",
                "item_id": f"{platform_prefix}_{platform_video_id}",
                "platform": platform,
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
                    "music_is_original": bool(item.get("musicMeta.musicOriginal", (item.get("musicMeta") or {}).get("musicOriginal", False))),
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
    parser = argparse.ArgumentParser(
        description="Làm sạch URL video từ TikTok, YouTube và Facebook."
    )
    parser.add_argument(
        "--directory",
        default=".",
        help="Thư mục chứa raw_dataDDMM.json; mặc định là thư mục hiện tại.",
    )
    args = parser.parse_args()

    try:
        input_file, date_token = find_input_file(Path(args.directory).resolve())
        with input_file.open("r", encoding="utf-8") as input_handle:
            input_data = json.load(input_handle)
        if not isinstance(input_data, list):
            raise ValueError("JSON đầu vào phải là một danh sách records.")
        confirm_input(input_file, len(input_data))
        output_file = next_output_path(input_file.parent, date_token)
        process_and_export_urls(str(input_file), str(output_file))
        print(f"[+] Output: {output_file}")
    except (FileNotFoundError, json.JSONDecodeError, RuntimeError, ValueError) as error:
        print(f"[-] {error}")