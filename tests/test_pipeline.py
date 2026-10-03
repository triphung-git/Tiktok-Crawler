"""Tests for pipeline module and end-to-end integration."""

import json
import tempfile
from pathlib import Path
import pytest
from src.pipeline.run import PipelineRunner
from src.storage.json_storage import load_json


def test_pipeline_runner_batch_determination():
    runner = PipelineRunner()

    # Explicit valid batch
    assert runner.determine_batch_name("WEEK3_0309") == "WEEK3_0309"
    assert runner.determine_batch_name("WEEK10_1212") == "WEEK10_1212"

    # Invalid batch raises ValueError
    with pytest.raises(ValueError):
        runner.determine_batch_name("INVALID_BATCH")

    # None produces current date format WEEK1_DDMM
    default_batch = runner.determine_batch_name(None)
    assert default_batch.startswith("WEEK1_")


def test_pipeline_process_urls():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        raw_file = tmp_path / "raw_data0309.json"
        raw_data = [
            {
                "webVideoUrl": "https://www.tiktok.com/@vtv24news/video/7391234567890",
                "videoMeta": {"duration": 60.0},
                "text": "Bản tin tối",
            }
        ]
        with open(raw_file, "w", encoding="utf-8") as f:
            json.dump(raw_data, f)

        runner = PipelineRunner()
        result = runner.run_process_urls(
            input_file=raw_file,
            batch_name="WEEK3_0309",
            dry_run=True,
        )

        assert result["report"]["valid_records"] == 1
        assert len(result["tasks"]) == 1
        assert result["tasks"][0]["task_id"] == "ID_0001"
