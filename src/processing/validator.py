"""Validation and deduplication rules for crawled data records."""

import math
import re
from typing import Any, Dict, Optional, Set, Tuple

from src.processing.cleaner import detect_platform, extract_video_id, sanitize_video_url


def reject_record(index: int, reason: str, raw_url: Any = "", message: str = "") -> Dict[str, Any]:
    """Tạo record bị loại bỏ kèm lý do chuẩn hóa."""
    return {
        "record_index": index,
        "status": "rejected",
        "reason": reason,
        "raw_url": raw_url,
        "message": message,
    }


def validate_batch_name(batch_name: str) -> bool:
    """Kiểm tra tên batch theo quy chuẩn WEEK<number>_<DDMM>."""
    if not isinstance(batch_name, str):
        return False
    return bool(re.fullmatch(r"WEEK\d+_\d{4}", batch_name.strip(), re.IGNORECASE))


def validate_record(
    item: Any,
    index: int,
    seen_urls: Optional[Set[str]] = None,
    global_urls: Optional[Set[str]] = None,
) -> Tuple[bool, Optional[str], Optional[str], Optional[str], Optional[Dict[str, Any]]]:
    """
    Kiểm định toàn diện 1 record:
    - Loại dữ liệu (dict)
    - Sự hiện diện của URL
    - Hỗ trợ platform
    - Tính hợp lệ của URL sau làm sạch
    - Chống trùng lặp 2 tầng: in-batch và cross-batch global
    - Video ID
    - Thời lượng (duration)

    Returns:
        (is_valid, clean_url, platform, video_id, reject_dict_if_invalid)
    """
    if seen_urls is None:
        seen_urls = set()
    if global_urls is None:
        global_urls = set()

    if not isinstance(item, dict):
        return False, None, None, None, reject_record(index, "invalid_record", message="Record không phải object.")

    raw_url = item.get("webVideoUrl") or item.get("video_url") or item.get("url")
    if not isinstance(raw_url, str) or not raw_url.strip():
        return False, None, None, None, reject_record(
            index, "missing_url", raw_url=raw_url, message="Thiếu trường URL video (webVideoUrl hoặc video_url)."
        )

    platform = detect_platform(raw_url)
    if not platform:
        return False, None, None, None, reject_record(
            index, "unsupported_platform", raw_url=raw_url, message="Domain không được hỗ trợ."
        )

    clean_url = sanitize_video_url(raw_url)
    if not clean_url:
        return False, None, None, None, reject_record(
            index, "invalid_url", raw_url=raw_url, message="URL không hợp lệ sau chuẩn hóa."
        )

    if clean_url in global_urls:
        return False, None, None, None, reject_record(
            index, "global_duplicate_url", raw_url=raw_url, message=f"URL đã tồn tại trong batch trước đó: {clean_url}"
        )

    if clean_url in seen_urls:
        return False, None, None, None, reject_record(
            index, "duplicate_url", raw_url=raw_url, message=f"Trùng URL chuẩn hóa trong batch: {clean_url}"
        )

    video_id = extract_video_id(clean_url, item, platform)
    if not video_id:
        return False, None, None, None, reject_record(
            index, "missing_video_id", raw_url=raw_url, message="Không trích xuất được video ID."
        )

    duration = (
        item.get("videoMeta.duration")
        or (item.get("videoMeta") or {}).get("duration")
        or item.get("duration")
        or item.get("duration_seconds")
    )
    if duration is not None:
        try:
            duration_val = float(duration)
            if not math.isfinite(duration_val) or duration_val < 0:
                raise ValueError
        except (TypeError, ValueError):
            return False, None, None, None, reject_record(
                index, "invalid_duration", raw_url=raw_url, message="Duration phải là số không âm."
            )

    return True, clean_url, platform, video_id, None


def classify_error(message: str) -> Tuple[str, bool]:
    """Phân loại lỗi download/xử lý và chỉ định khả năng retry."""
    message = str(message).lower()
    if "unable to connect to proxy" in message or "proxyerror" in message or " over proxy " in message:
        return "proxy_error", False
    if "universal data for rehydration" in message or "unable to extract" in message:
        return "extractor_error", True
    if "429" in message or "rate limit" in message or "too many requests" in message:
        return "rate_limited", True
    if "timeout" in message or "timed out" in message:
        return "timeout", True
    if "private" in message or "not available" in message or "unavailable" in message:
        return "unavailable", False
    return "processing_error", False
