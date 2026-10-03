"""Tests for validator module: record validation, deduplication, batch naming, error classification."""

import pytest
from src.processing.validator import (
    classify_error,
    reject_record,
    validate_batch_name,
    validate_record,
)


def test_validate_batch_name():
    assert validate_batch_name("WEEK3_0309") is True
    assert validate_batch_name("week1_1409") is True
    assert validate_batch_name("WEEK12_3112") is True
    assert validate_batch_name("BATCH1") is False
    assert validate_batch_name("WEEK3") is False
    assert validate_batch_name("WEEK_0309") is False
    assert validate_batch_name("") is False


def test_classify_error():
    err_class, retryable = classify_error("HTTP 429 Too Many Requests")
    assert err_class == "rate_limited" and retryable is True

    err_class, retryable = classify_error("Connection timed out")
    assert err_class == "timeout" and retryable is True

    err_class, retryable = classify_error("Unable to connect to proxy")
    assert err_class == "proxy_error" and retryable is False

    err_class, retryable = classify_error("Video is private or unavailable")
    assert err_class == "unavailable" and retryable is False

    err_class, retryable = classify_error("Random Python Exception")
    assert err_class == "processing_error" and retryable is False


def test_validate_record_success():
    item = {
        "webVideoUrl": "https://www.tiktok.com/@vtv24news/video/7391234567890?param=1",
        "videoMeta": {"duration": 45.0},
    }
    is_valid, clean_url, platform, video_id, reject = validate_record(item, 1)
    assert is_valid is True
    assert clean_url == "https://www.tiktok.com/@vtv24news/video/7391234567890"
    assert platform == "tiktok"
    assert video_id == "7391234567890"
    assert reject is None


def test_validate_record_missing_url():
    item = {"videoMeta": {"duration": 45.0}}
    is_valid, clean_url, platform, video_id, reject = validate_record(item, 1)
    assert is_valid is False
    assert reject["reason"] == "missing_url"


def test_validate_record_unsupported_platform():
    item = {"webVideoUrl": "https://unknown.com/video/123"}
    is_valid, clean_url, platform, video_id, reject = validate_record(item, 1)
    assert is_valid is False
    assert reject["reason"] == "unsupported_platform"


def test_validate_record_in_batch_duplicate():
    item = {"webVideoUrl": "https://www.tiktok.com/@vtv24news/video/7391234567890"}
    seen_urls = {"https://www.tiktok.com/@vtv24news/video/7391234567890"}
    is_valid, clean_url, platform, video_id, reject = validate_record(item, 1, seen_urls=seen_urls)
    assert is_valid is False
    assert reject["reason"] == "duplicate_url"


def test_validate_record_global_duplicate():
    item = {"webVideoUrl": "https://www.tiktok.com/@vtv24news/video/7391234567890"}
    global_urls = {"https://www.tiktok.com/@vtv24news/video/7391234567890"}
    is_valid, clean_url, platform, video_id, reject = validate_record(item, 1, global_urls=global_urls)
    assert is_valid is False
    assert reject["reason"] == "global_duplicate_url"


def test_validate_record_invalid_duration():
    item = {
        "webVideoUrl": "https://www.tiktok.com/@vtv24news/video/7391234567890",
        "videoMeta": {"duration": -5},
    }
    is_valid, clean_url, platform, video_id, reject = validate_record(item, 1)
    assert is_valid is False
    assert reject["reason"] == "invalid_duration"
