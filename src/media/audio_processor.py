"""Audio processing engine: normalization, vocal separation, denoising, and VAD segmentation."""

import gc
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.config import get_config, resolve_path
from src.media.audio_downloader import AudioDownloader
from src.processing.validator import classify_error
from src.storage.json_storage import MetadataManager, atomic_write_json

# Import AI models
try:
    from models.source_separator import separate_vocals
except ModuleNotFoundError:
    separate_vocals = None

try:
    from models.speech_denoiser import enhance_audio
except ModuleNotFoundError:
    enhance_audio = None

try:
    from models.vad_segmenter import slice_and_save
except ModuleNotFoundError:
    slice_and_save = None


class Heartbeat:
    """In nhịp tim định kỳ khi inference C++ đang chạy, tránh cảm giác bị treo."""
    def __init__(self, label: str, interval: float = 15.0):
        self.label = label
        self.interval = interval
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def _run(self) -> None:
        start = time.time()
        while not self._stop_event.wait(self.interval):
            elapsed = time.time() - start
            print(f"    ... {self.label}: đã chạy {elapsed:.0f}s")

    def __enter__(self) -> "Heartbeat":
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=1.0)


class AudioProcessor:
    """Bộ xử lý Audio toàn diện từ chuẩn hóa, tách nhạc, khử nhiễu đến cắt lát câu thoại."""

    def __init__(self, output_dir: str | Path, config_override: Optional[Dict[str, Any]] = None):
        self.config = get_config()
        if config_override:
            self.config.update(config_override)

        self.output_dir = Path(output_dir).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.segments_dir = self.output_dir / "segments"
        self.metadata_file = self.output_dir / "metadata.json"

        # Resolve binary paths
        ffmpeg_name = self.config.get("paths", {}).get("ffmpeg_path", "ffmpeg.exe")
        ffprobe_name = self.config.get("paths", {}).get("ffprobe_path", "ffprobe.exe")
        self.ffmpeg_path = str(resolve_path(ffmpeg_name))
        self.ffprobe_path = str(resolve_path(ffprobe_name))

        # Metadata manager
        self.metadata_mgr = MetadataManager(self.metadata_file)
        self.downloader = AudioDownloader()

        # Thread synchronization
        self.inference_lock = threading.Lock()
        self.clean_temp_files()

    def clean_temp_files(self) -> None:
        """Dọn dẹp file tạm tàn dư từ các lần chạy trước."""
        if not self.output_dir.is_dir():
            return
        for file in self.output_dir.iterdir():
            if file.is_file() and (file.name.startswith(".download_") or (file.name.startswith(".") and ".part" in file.name)):
                try:
                    file.unlink()
                except OSError:
                    pass

    def run_command(self, command: List[str], timeout: int = 300) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(command, capture_output=True, text=True, check=True, timeout=timeout)
        except subprocess.CalledProcessError as error:
            details = (error.stderr or error.stdout or "Không có log từ tiến trình.").strip()
            raise RuntimeError(f"Media command thất bại (exit {error.returncode}): {details[-2000:]}") from error

    def probe_wav(self, path: str | Path) -> float:
        """Kiểm định định dạng WAV 16kHz mono PCM 16-bit và trích xuất duration."""
        process = self.run_command([
            self.ffprobe_path, "-v", "quiet", "-print_format", "json",
            "-show_streams", "-show_format", str(path)
        ], timeout=60)

        data = json.loads(process.stdout)
        stream = next((item for item in data.get("streams", []) if item.get("codec_type") == "audio"), None)
        if not stream:
            raise ValueError("Không tìm thấy luồng audio trong file.")

        if (str(stream.get("sample_rate")) != "16000" or int(stream.get("channels", 0)) != 1
                or stream.get("codec_name") != "pcm_s16le"):
            raise ValueError("Kiểm định thất bại: audio bắt buộc phải là WAV PCM_16, mono, 16 kHz.")

        duration = float(data.get("format", {}).get("duration") or 0)
        if duration <= 0:
            raise ValueError("Audio rỗng hoặc không có duration hợp lệ.")
        return duration

    def build_metadata(
        self,
        task: Dict[str, Any],
        audio_path: Path,
        duration: float,
        source_duration: float,
        duration_mismatch: Optional[float],
        segments: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        video_id = str(task.get("platform_video_id") or "")
        if not video_id:
            match = re.search(r"/video/(\d+)", task.get("original_url", ""))
            video_id = match.group(1) if match else ""

        record = {
            "item_id": task.get("item_id") or f"tt_{video_id}",
            "task_id": task.get("task_id", ""),
            "platform": task.get("platform", "tiktok"),
            "platform_video_id": video_id,
            "video_url": task.get("original_url", ""),
            "title": task.get("title", ""),
            "description": task.get("description", ""),
            "posted_at": task.get("posted_at"),
            "language_raw": task.get("language_raw") or task.get("text_language", "unknown"),
            "audio_path": str(audio_path.relative_to(resolve_path("."))).replace(os.sep, "/") if audio_path.is_relative_to(resolve_path(".")) else str(audio_path),
            "duration_seconds": round(duration, 2),
            "source_duration_seconds": round(source_duration, 2),
            "crawl_batch": task.get("crawl_batch", "tt_batch_01"),
            "crawled_at": task.get("crawled_at") or datetime.now(timezone.utc).isoformat(),
            "platform_meta": task.get("platform_meta", {}),
            "language_region": task.get("language_region", "mixed"),
            "enhancement_status": "success",
            "enhancement_model": "dpdfnet8.onnx",
            "vocal_separation_model": "UVR-MDX-NET-Voc_FT.onnx",
        }
        if duration_mismatch is not None:
            record["duration_mismatch_seconds"] = round(duration_mismatch, 2)
        if segments:
            record["segments"] = segments
            record["segment_count"] = len(segments)
            record["total_speech_duration"] = round(sum(s.get("duration", 0) for s in segments), 2)
        return record

    def process_task(self, task: Dict[str, Any], enable_vad: bool = True) -> Dict[str, Any]:
        """Thực thi pipeline xử lý 1 task: Download -> Loudnorm -> UVR -> DPDFNet -> VAD Slicing."""
        task_id = re.sub(r"[^A-Za-z0-9_.-]", "_", str(task.get("task_id", "UNKNOWN_ID")))
        result = {**task, "status": "failed", "error_message": "", "local_path": ""}
        final_file = self.output_dir / f"{task_id}.wav"
        token = uuid.uuid4().hex

        wav_temp = self.output_dir / f".{task_id}.{token}.wav.part"
        vocal_temp = self.output_dir / f".{task_id}.{token}.vocal.wav.part"
        enhanced_temp = self.output_dir / f".{task_id}.{token}.enhanced.wav.part"
        downloaded: Optional[str] = None

        # Check resume: nếu đã có file và metadata
        existing = self.metadata_mgr.get_record(str(task.get("item_id") or ""))
        if final_file.is_file() and final_file.stat().st_size > 0:
            dur = existing.get("duration_seconds") if existing else self.probe_wav(final_file)
            return {
                **result,
                "status": "success",
                "local_path": str(final_file),
                "metadata_path": str(self.metadata_file),
                "resumed": True,
                "duration_seconds": dur,
            }

        try:
            if not isinstance(task.get("original_url"), str) or not task["original_url"]:
                raise ValueError("Task không có original_url hợp lệ.")
            if not os.path.isfile(self.ffmpeg_path) or not os.path.isfile(self.ffprobe_path):
                raise FileNotFoundError(f"Không tìm thấy ffmpeg ({self.ffmpeg_path}) hoặc ffprobe ({self.ffprobe_path}).")
            if separate_vocals is None or enhance_audio is None:
                raise RuntimeError("Thiếu runtime ONNX cho UVR hoặc DPDFNet. Kiểm tra cài đặt soundfile, sherpa-onnx.")

            print(f"\n[*] Task {task_id}: [1/5] Tải audio")
            downloaded = self.downloader.download(task["original_url"], self.output_dir, task_id)

            print("  [2/5] Chuẩn hóa 16kHz mono + EBU R128 loudnorm")
            self.run_command([
                self.ffmpeg_path, "-y", "-i", downloaded,
                "-af", "loudnorm=I=-16:TP=-1.0:LRA=11",
                "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", "-f", "wav", str(wav_temp),
            ], timeout=300)

            source_duration = self.probe_wav(wav_temp)
            print(f"  [3/5] Kiểm định audio đầu vào ({source_duration:.1f}s)")
            mismatch = None
            if task.get("duration_seconds") is not None:
                mismatch = abs(source_duration - float(task["duration_seconds"]))
                if mismatch <= 2:
                    mismatch = None
                else:
                    print(f"  [Cảnh báo] Duration lệch {mismatch:.2f}s.")

            # Tuần tự hóa bước 4 & 5 bằng INFERENCE_LOCK (giữ RAM < 3GB)
            with self.inference_lock:
                t_inf_start = time.time()
                print(f"  [4/5] Tách nhạc nền (UVR MDX-Net, audio: {source_duration:.1f}s)...")
                with Heartbeat(f"[Task {task_id}] [4/5] UVR MDX-Net ({source_duration:.1f}s)", interval=15.0):
                    t0 = time.time()
                    separate_vocals(wav_temp, vocal_temp)
                    t_uvr = time.time() - t0
                print(f"    [+] Tách nhạc hoàn tất trong {t_uvr:.1f}s")

                print(f"  [5/5] Khử nhiễu giọng nói (DPDFNet, audio: {source_duration:.1f}s)...")
                with Heartbeat(f"[Task {task_id}] [5/5] DPDFNet ({source_duration:.1f}s)", interval=15.0):
                    t0 = time.time()
                    enhance_audio(vocal_temp, enhanced_temp)
                    t_denoise = time.time() - t0
                print(f"    [+] Khử nhiễu hoàn tất trong {t_denoise:.1f}s (tổng inference: {time.time() - t_inf_start:.1f}s)")

            enhanced_duration = self.probe_wav(enhanced_temp)
            os.replace(enhanced_temp, final_file)
            print(f"  [+] Lưu audio hoàn chỉnh ({enhanced_duration:.1f}s) -> {final_file.name}")

            # Phân đoạn câu thoại VAD (nếu kích hoạt)
            segments = []
            if enable_vad and slice_and_save is not None:
                try:
                    self.segments_dir.mkdir(parents=True, exist_ok=True)
                    segments = slice_and_save(final_file, self.segments_dir, task_id)
                    print(f"  [+] VAD cắt được {len(segments)} segments câu thoại tự nhiên.")
                except Exception as vad_err:
                    print(f"  [!] VAD segmentation lỗi: {vad_err}")

            record = self.build_metadata(task, final_file, enhanced_duration, source_duration, mismatch, segments)
            self.metadata_mgr.update_record(record)
            self.metadata_mgr.flush()

            result.update({
                "status": "success",
                "local_path": str(final_file),
                "metadata_path": str(self.metadata_file),
                "duration_seconds": round(enhanced_duration, 2),
                "duration_mismatch_seconds": record.get("duration_mismatch_seconds"),
                "segments": segments,
            })

        except Exception as error:
            error_class, retryable = classify_error(str(error))
            result.update({"error_message": str(error), "error_class": error_class, "retryable": retryable})
            print(f"  [-] Task {task_id} ({error_class}): {error}")

        finally:
            for p in (downloaded, str(wav_temp), str(vocal_temp), str(enhanced_temp)):
                if p and os.path.exists(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass
            gc.collect()

        return result

    def write_summary_report(self, input_file: str, results: List[Dict[str, Any]]) -> str:
        successful = [item for item in results if item.get("status") == "success"]
        failed = [item for item in results if item.get("status") != "success"]
        total_audio = sum(item.get("duration_seconds", 0) for item in successful)

        report = {
            "input_file": str(Path(input_file).resolve()),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "total_tasks": len(results),
            "success": len(successful),
            "failed": len(failed),
            "total_audio_seconds": round(total_audio, 2),
            "total_audio_hours": round(total_audio / 3600, 3),
            "error_classes": dict(Counter(item.get("error_class", "unknown") for item in failed)),
            "duration_mismatch_warnings": sum(bool(item.get("duration_mismatch_seconds")) for item in results),
            "pipeline": "UVR-MDX-NET-Voc_FT -> DPDFNet -> Silero-VAD -> WAV-16kHz-mono",
        }
        summary_path = self.output_dir / "summary.json"
        atomic_write_json(summary_path, report)
        return str(summary_path)

    def run_batch(self, tasks: List[Dict[str, Any]], max_workers: int = 4, enable_vad: bool = True) -> Dict[str, Any]:
        worker_count = max(1, min(int(max_workers), 8))
        results: List[Dict[str, Any]] = []
        print(f"[*] Bắt đầu xử lý batch: {len(tasks)} task, {worker_count} worker song song...")

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {executor.submit(self.process_task, task, enable_vad): task for task in tasks}
            for done, future in enumerate(as_completed(futures), 1):
                task = futures[future]
                try:
                    result = future.result()
                except Exception as error:
                    error_class, _ = classify_error(str(error))
                    result = {**task, "status": "failed", "error_message": str(error), "error_class": error_class}

                results.append(result)
                dur_info = f", {result.get('duration_seconds', 0)}s" if result.get('status') == 'success' else ""
                print(f"[*] Tiến độ {done}/{len(tasks)}: {result.get('task_id')} -> {result['status']}{dur_info}")

        self.metadata_mgr.flush()
        failed = [item for item in results if item.get("status") != "success"]
        if failed:
            atomic_write_json(self.output_dir / "failed_tasks.json", failed)

        report_file = self.write_summary_report(str(self.output_dir), results)
        successful = [item for item in results if item.get("status") == "success"]
        total_audio = sum(item.get("duration_seconds", 0) for item in successful)

        return {
            "total": len(tasks),
            "success": len(successful),
            "failed": len(failed),
            "total_audio_seconds": round(total_audio, 2),
            "total_audio_hours": round(total_audio / 3600, 3),
            "report_file": report_file,
            "metadata_file": str(self.metadata_file),
            "output_dir": str(self.output_dir),
        }
