"""Tests for cleaner module: URL sanitization, dialect inference, duration formatting."""

import pytest
from src.processing.cleaner import (
    clean_text,
    detect_platform,
    extract_video_id,
    format_duration,
    infer_regional_dialect,
    sanitize_video_url,
)


def test_detect_platform():
    assert detect_platform("https://www.tiktok.com/@user/video/123456789") == "tiktok"
    assert detect_platform("https://tiktok.com/@user/video/123456789") == "tiktok"
    assert detect_platform("https://www.youtube.com/watch?v=abcdef") == "youtube"
    assert detect_platform("https://youtu.be/abcdef") == "youtube"
    assert detect_platform("https://www.facebook.com/watch?v=999") == "facebook"
    assert detect_platform("https://fb.watch/xyz") == "facebook"
    assert detect_platform("https://fake-tiktok.com/video/123") is None
    assert detect_platform("not_a_url") is None
    assert detect_platform("") is None


def test_sanitize_video_url():
    tiktok_raw = "https://www.tiktok.com/@vtv24news/video/7391234567890?is_from_webapp=1&sender_device=pc"
    assert sanitize_video_url(tiktok_raw) == "https://www.tiktok.com/@vtv24news/video/7391234567890"

    yt_raw = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s&feature=shared"
    assert sanitize_video_url(yt_raw) == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    invalid_url = "https://unknown-domain.com/video/123"
    assert sanitize_video_url(invalid_url) is None


def test_format_duration():
    assert format_duration(45) == "00:45"
    assert format_duration(125) == "02:05"
    assert format_duration(3665) == "01:01:05"
    assert format_duration("72.5") == "01:12"
    assert format_duration(None) is None
    assert format_duration(-10) is None
    assert format_duration("invalid") is None


def test_infer_regional_dialect():
    # Northern markers: bo, me, qua, ngo, lac, thia, coc, dua, bao
    assert infer_regional_dialect("Mẹ nấu cho em bát ngô luộc ngon quá") == "northern"

    # Central markers: mo, te, rang, rua, ni, no, ri, tau, mi, chi, man
    assert infer_regional_dialect("Răng mà đi mô rồi nì, mi mần chi rứa") == "central"

    # Southern markers: ma, ba, trai, bap, dau phong, muong, ly, thom, hong, nghen
    assert infer_regional_dialect("Ba má mua ly bắp xào thơm nghen") == "southern"

    # Unidentified
    assert infer_regional_dialect("Hello world 12345") == "unidentified"
    assert infer_regional_dialect("") == "unidentified"


def test_extract_video_id():
    url = "https://www.tiktok.com/@user/video/7391234567890"
    assert extract_video_id(url, {}, "tiktok") == "7391234567890"
    assert extract_video_id(url, {"id": "custom_id"}, "tiktok") == "custom_id"

    yt_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert extract_video_id(yt_url, {}, "youtube") == "dQw4w9WgXcQ"


def test_clean_text():
    assert clean_text("  Xin chào \n\n các bạn \t!   ") == "Xin chào các bạn !"
    assert clean_text(None) == ""
