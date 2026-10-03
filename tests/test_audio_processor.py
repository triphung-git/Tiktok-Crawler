"""Tests for audio_processor module."""

import tempfile
from pathlib import Path
import numpy as np
import pytest
import soundfile as sf
from src.media.audio_processor import AudioProcessor


def test_probe_wav_and_metadata_generation():
    with tempfile.TemporaryDirectory() as tmp_dir:
        output_dir = Path(tmp_dir)
        processor = AudioProcessor(output_dir)

        # Tạo file WAV chuẩn 16kHz mono PCM_16
        sample_rate = 16000
        duration_s = 2.5
        samples = (np.sin(2 * np.pi * 440 * np.linspace(0, duration_s, int(sample_rate * duration_s))) * 32767).astype(np.int16)
        test_wav = output_dir / "test_tone.wav"
        sf.write(str(test_wav), samples, sample_rate, subtype="PCM_16")

        # Test probe_wav
        dur = processor.probe_wav(test_wav)
        assert abs(dur - duration_s) < 0.1

        # Test build_metadata
        task = {
            "task_id": "ID_0001",
            "item_id": "tt_123456",
            "original_url": "https://tiktok.com/@u/video/123456",
            "duration_seconds": 2.5,
            "crawl_batch": "WEEK3_0309",
        }
        segments = [{"filename": "ID_0001_seg001.wav", "duration": 2.5, "start": 0.0, "end": 2.5}]
        meta = processor.build_metadata(task, test_wav, dur, dur, None, segments=segments)

        assert meta["item_id"] == "tt_123456"
        assert meta["duration_seconds"] == round(dur, 2)
        assert meta["segment_count"] == 1
        assert meta["enhancement_status"] == "success"


def test_clean_temp_files():
    with tempfile.TemporaryDirectory() as tmp_dir:
        output_dir = Path(tmp_dir)
        temp_file1 = output_dir / ".download_ID_0001_abc.tmp"
        temp_file2 = output_dir / ".ID_0001.part"
        valid_file = output_dir / "ID_0001.wav"

        temp_file1.write_text("temp", encoding="utf-8")
        temp_file2.write_text("temp", encoding="utf-8")
        valid_file.write_text("valid", encoding="utf-8")

        processor = AudioProcessor(output_dir)
        processor.clean_temp_files()

        assert not temp_file1.exists()
        assert not temp_file2.exists()
        assert valid_file.exists()
