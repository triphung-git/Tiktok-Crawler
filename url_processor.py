import json
import math
import os
import re
import unicodedata
import argparse
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter
from typing import Any, Optional
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
        names = ", ".join(candidate.name for candidate in candidates)
        raise ValueError(
            f"Thư mục có nhiều file input ({names}). Hãy dùng --input để chọn một file."
        )
    selected = candidates[0]
    date_token = re.fullmatch(r"raw_data(\d{4})\.json", selected.name).group(1)
    return selected, date_token


def load_input_records(input_file: Path) -> list[dict[str, Any]]:
    with input_file.open("r", encoding="utf-8") as input_handle:
        data = json.load(input_handle)
    if not isinstance(data, list):
        raise ValueError("JSON đầu vào phải là một danh sách records.")
    return data


def confirm_input(input_file: Path, record_count: int) -> None:
    print(f"\nFile input: {input_file}")
    print(f"Số records: {record_count}")
    answer = input("Xác nhận xử lý file này? [y/N]: ").strip().lower()
    if answer not in {"y", "yes"}:
        raise RuntimeError("Đã hủy xử lý theo xác nhận của người dùng.")


def reject_record(index: int, reason: str, raw_url: Any = "", message: str = "") -> dict[str, Any]:
    return {
        "record_index": index,
        "status": "rejected",
        "reason": reason,
        "raw_url": raw_url,
        "message": message,
    }


def build_task(item: dict[str, Any], clean_url: str, platform: str, task_number: int,
               crawl_batch: str, crawled_at: str) -> dict[str, Any]:
    video_meta = item.get("videoMeta") or {}
    duration_seconds = item.get("videoMeta.duration", video_meta.get("duration"))
    text_language = item.get("textLanguage") or "unknown"
    language_region = infer_regional_dialect(item.get("text", ""))
    platform_video_id = extract_video_id(clean_url, item, platform)
    subtitle_links = item.get("videoMeta.subtitleLinks", video_meta.get("subtitleLinks")) or []
    platform_prefix = {"tiktok": "tt", "youtube": "yt", "facebook": "fb"}[platform]

    return {
        "task_id": f"ID_{task_number:04d}",
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
            "has_platform_captions": bool(subtitle_links),
        },
    }


def process_records(
    data: list[Any],
    crawl_batch: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    tasks = []
    rejected = []
    seen_urls = set()
    crawled_at = datetime.now(timezone.utc).isoformat()

    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            rejected.append(reject_record(index, "invalid_record", message="Record không phải object."))
            continue
        raw_url = item.get("webVideoUrl")
        if not isinstance(raw_url, str) or not raw_url.strip():
            rejected.append(reject_record(index, "missing_url", raw_url=raw_url, message="Thiếu trường webVideoUrl."))
            continue
        platform = detect_platform(raw_url)
        if not platform:
            rejected.append(reject_record(index, "unsupported_platform", raw_url=raw_url, message="Domain không được hỗ trợ."))
            continue
        clean_url = sanitize_video_url(raw_url)
        if not clean_url:
            rejected.append(reject_record(index, "invalid_url", raw_url=raw_url, message="URL không hợp lệ."))
            continue
        if clean_url in seen_urls:
            rejected.append(reject_record(index, "duplicate_url", raw_url=raw_url, message=f"Trùng URL chuẩn hóa: {clean_url}"))
            continue
        platform_video_id = extract_video_id(clean_url, item, platform)
        if not platform_video_id:
            rejected.append(reject_record(index, "missing_video_id", raw_url=raw_url, message="Không trích xuất được video ID."))
            continue
        duration = item.get("videoMeta.duration", (item.get("videoMeta") or {}).get("duration"))
        if duration is not None:
            try:
                duration_value = float(duration)
                if not math.isfinite(duration_value) or duration_value < 0:
                    raise ValueError
            except (TypeError, ValueError):
                rejected.append(reject_record(index, "invalid_duration", raw_url=raw_url, message="Duration phải là số không âm."))
                continue
        seen_urls.add(clean_url)
        tasks.append(build_task(item, clean_url, platform, len(tasks) + 1, crawl_batch, crawled_at))
    return tasks, rejected


def atomic_write_json(path: Path, data: Any) -> None:
    temp_path = path.with_name(f".{path.name}.part")
    with temp_path.open("w", encoding="utf-8") as output_handle:
        json.dump(data, output_handle, ensure_ascii=False, indent=4)
        output_handle.write("\n")
    os.replace(temp_path, path)


def process_and_export_urls(
    input_file: str,
    output_file: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    input_path = Path(input_file)
    data = load_input_records(input_path)
    tasks, rejected = process_records(
        data,
        os.getenv("CRAWL_BATCH", "tt_batch_01"),
    )
    output_path = Path(output_file)
    report = {
        "input_file": str(input_path),
        "output_file": str(output_path),
        "total_records": len(data),
        "valid_records": len(tasks),
        "rejected_records": len(rejected),
        "reasons": dict(Counter(item["reason"] for item in rejected)),
        "dry_run": dry_run,
    }
    if not dry_run:
        atomic_write_json(output_path, tasks)
        output_stem = output_path.stem.removeprefix("sources_")
        atomic_write_json(output_path.with_name(f"processing_report_{output_stem}.json"), report)
    print(f"[+] {input_path.name}: {len(tasks)} hợp lệ, {len(rejected)} bị loại.")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Làm sạch URL video từ TikTok, YouTube và Facebook."
    )
    parser.add_argument(
        "--directory",
        default=".",
        help="Thư mục cần xử lý; mặc định là thư mục hiện tại.",
    )
    parser.add_argument(
        "--input",
        help="Xử lý chính xác một file raw_dataDDMM.json; ghi đè --directory.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chỉ kiểm tra và in báo cáo, không ghi output.",
    )
    args = parser.parse_args()
    root = Path(args.directory).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Không tìm thấy thư mục: {root}")
    if args.input:
        selected_input = Path(args.input).resolve()
        if not selected_input.is_file():
            raise FileNotFoundError(f"Không tìm thấy file input: {selected_input}")
        match = re.fullmatch(r"raw_data(\d{4})\.json", selected_input.name)
        if not match:
            raise ValueError("File input phải có tên dạng raw_dataDDMM.json.")
        input_file, date_token = selected_input, match.group(1)
    else:
        input_file, date_token = find_input_file(root)

    record_count = len(load_input_records(input_file))
    confirm_input(input_file, record_count)
    output_file = next_output_path(input_file.parent, date_token)
    process_and_export_urls(str(input_file), str(output_file), args.dry_run)
    if not args.dry_run:
        print(f"[+] Output: {output_file}")


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, json.JSONDecodeError, RuntimeError, ValueError) as error:
        print(f"[-] {error}")