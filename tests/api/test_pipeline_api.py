"""API Contract & Resilience Testing.

Tests JSON schema conformity, HTTP status code handling, rate limit error
classification, and payload contract validation for TikTok pipeline.
"""

import pytest
from src.processing.validator import classify_error, validate_record
from src.processing.transformer import build_task


def test_api_contract_crawled_record_success():
    """TC-API-01: Verify valid crawled record complies with schema and contract."""
    raw_item = {
        "webVideoUrl": "https://www.tiktok.com/@vtv24news/video/7234567890123456789?is_from_webapp=1",
        "text": "Bản tin thời sự VTV24 hôm nay tại Hà Nội",
        "videoMeta": {"duration": 45.0},
        "author": "vtv24news",
    }
    is_valid, clean_url, platform, video_id, reject = validate_record(raw_item, index=1)
    
    assert is_valid is True
    assert clean_url == "https://www.tiktok.com/@vtv24news/video/7234567890123456789"
    assert platform == "tiktok"
    assert video_id == "7234567890123456789"
    assert reject is None


def test_api_contract_missing_mandatory_fields():
    """TC-API-01 (Negative): Verify missing required fields fail contract validation."""
    invalid_record = {
        # Missing 'webVideoUrl' or 'url'
        "text": "Video without url",
        "videoMeta": {"duration": 20.0},
    }
    is_valid, clean_url, platform, video_id, reject = validate_record(invalid_record, index=1)
    assert is_valid is False
    assert reject["reason"] == "missing_url"


def test_api_contract_task_output_schema():
    """TC-API-06: Verify generated task schema adheres to downstream media worker expectations."""
    raw_item = {
        "text": "Bản tin thời sự tối nay tại Hà Nội",
        "videoMeta": {"duration": 120.0},
        "createTimeISO": "2026-09-01T12:00:00Z",
        "author": "vtv24news",
    }
    task = build_task(
        item=raw_item,
        clean_url="https://www.tiktok.com/@vtv24news/video/7391234567890",
        platform="tiktok",
        task_number=1,
        crawl_batch="WEEK3_0309",
        crawled_at="2026-09-03T10:00:00Z",
    )

    # Contract Assertions
    assert isinstance(task, dict)
    assert task["task_id"] == "ID_0001"
    assert task["item_id"] == "tt_7391234567890"
    assert task["platform"] == "tiktok"
    assert task["crawl_batch"] == "WEEK3_0309"
    assert task["duration_formatted"] == "02:00"
    assert task["platform_meta"]["author"] == "vtv24news"


def test_http_429_rate_limit_classification():
    """TC-API-03: Verify HTTP 429 Too Many Requests is correctly classified as retryable rate limit."""
    error_messages = [
        "HTTP 429 Too Many Requests",
        "TikTok API 429 rate limit exceeded",
    ]
    for msg in error_messages:
        err_class, retryable = classify_error(msg)
        assert err_class == "rate_limited", f"Expected rate_limited for: {msg}"
        assert retryable is True, f"Expected retryable=True for: {msg}"


def test_http_network_timeout_classification():
    """TC-API-03: Verify network timeouts are classified as retryable."""
    timeout_errors = [
        "Connection timed out",
        "ReadTimeoutError on socket",
    ]
    for msg in timeout_errors:
        err_class, retryable = classify_error(msg)
        assert err_class == "timeout"
        assert retryable is True


def test_http_unavailable_and_proxy_classification():
    """TC-API-05: Verify non-retryable errors are correctly flagged."""
    err_class, retryable = classify_error("Video is private or unavailable")
    assert err_class == "unavailable"
    assert retryable is False

    err_class, retryable = classify_error("Unable to connect to proxy")
    assert err_class == "proxy_error"
    assert retryable is False
