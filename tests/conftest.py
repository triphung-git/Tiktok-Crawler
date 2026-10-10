"""Pytest root configuration and shared fixtures for Quality Engineering test suite."""

import sys
from pathlib import Path
import pytest

# Ensure project root is always in Python path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


@pytest.fixture
def sample_video_record():
    """Provides a valid crawled TikTok video item for testing."""
    return {
        "url": "https://www.tiktok.com/@vtv24news/video/7234567890123456789?is_from_webapp=1&sender_device=pc",
        "title": "Bản tin thời sự VTV24 hôm nay tại Hà Nội",
        "duration": 45.0,
        "author": "vtv24news",
        "crawled_at": "2026-10-10T20:00:00Z",
    }


@pytest.fixture
def sample_json_schema():
    """Defines JSON schema standard for pipeline task items."""
    return {
        "type": "object",
        "required": ["task_id", "url", "platform", "crawl_batch"],
        "properties": {
            "task_id": {"type": "string"},
            "item_id": {"type": "string"},
            "url": {"type": "string", "format": "uri"},
            "platform": {"type": "string", "enum": ["tiktok", "youtube", "facebook"]},
            "title": {"type": "string"},
            "duration": {"type": "number", "minimum": 0},
            "language_region": {
                "type": "string",
                "enum": ["northern", "central", "southern", "unidentified"],
            },
            "crawl_batch": {"type": "string"},
        },
    }
