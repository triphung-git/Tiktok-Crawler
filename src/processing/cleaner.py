"""URL and text cleaning utilities for TikTok and social media video records."""

import re
import unicodedata
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

SUPPORTED_DOMAINS = {
    "tiktok.com": "tiktok",
    "youtube.com": "youtube",
    "youtu.be": "youtube",
    "facebook.com": "facebook",
    "fb.watch": "facebook",
}

REGIONAL_MARKERS = {
    "northern": {
        "bo", "me", "qua", "ngo", "lac", "thia", "coc", "dua", "bao"
    },
    "central": {
        "mo", "te", "rang", "rua", "ni", "no", "ri", "tau", "mi", "chi", "man"
    },
    "southern": {
        "ma", "ba", "trai", "bap", "dau phong", "muong", "ly", "thom", "hong", "nghen"
    }
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
    """Làm sạch URL, loại bỏ query parameter rác và chuẩn hóa URL canonical."""
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


def format_duration(duration_seconds: Any) -> Optional[str]:
    """Chuyển thời lượng tính bằng giây sang định dạng HH:MM:SS hoặc MM:SS."""
    if duration_seconds is None:
        return None

    try:
        total_seconds = int(float(duration_seconds))
    except (TypeError, ValueError):
        return None

    if total_seconds < 0:
        return None

    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def infer_regional_dialect(text: str) -> str:
    """Suy đoán vùng miền từ caption theo bộ giá trị language_region."""
    if not isinstance(text, str) or not text.strip():
        return "unidentified"

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
        return "unidentified"
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


def clean_text(text: str) -> str:
    """Làm sạch khoảng trắng thừa và ký tự điều khiển trong văn bản."""
    if not isinstance(text, str):
        return ""
    text = re.sub(r"[\r\n\t]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()
