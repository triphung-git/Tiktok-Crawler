"""Tests for audio_downloader module."""

import pytest
from src.media.audio_downloader import AudioDownloader
from src.processing.validator import classify_error


def test_audio_downloader_init():
    downloader = AudioDownloader()
    assert downloader.attempts >= 1
    assert downloader.socket_timeout >= 10


def test_error_classification_for_retries():
    # Retryable errors
    _, retryable = classify_error("HTTP Error 429: Too Many Requests")
    assert retryable is True

    _, retryable = classify_error("Read timed out. (read timeout=60)")
    assert retryable is True

    # Non-retryable errors
    _, retryable = classify_error("Video is private or removed by author")
    assert retryable is False

    _, retryable = classify_error("ProxyError: Cannot connect to proxy")
    assert retryable is False
