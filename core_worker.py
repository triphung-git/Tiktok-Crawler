import argparse
import json
import os
import random
import re
import subprocess
import sys
import threading
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

try:
    import yt_dlp
except ModuleNotFoundError:
    yt_dlp = None

try:
    from models.speech_denoiser import enhance_audio
except ModuleNotFoundError:
    enhance_audio = None


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
FFMPEG_PATH = os.path.join(CURRENT_DIR, "ffmpeg.exe")
FFPROBE_PATH = os.path.join(CURRENT_DIR, "ffprobe.exe")
OUTPUT_DIR = ""
METADATA_FILE = ""
METADATA_LOCK = threading.Lock()
METADATA_BY_ITEM: dict[str, dict[str, Any]] = {}


def atomic_write_json(path: str, data: Any) -> None:
    temp_path = f"{path}.part"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(temp_path, path)


def load_tasks(input_file: str) -> list[dict[str, Any]]:
    with open(input_file, "r", encoding="utf-8") as handle:
        tasks = json.load(handle)
    if not isinstance(tasks, list):
        raise ValueError("sources.json phai chua mot JSON array.")
    return tasks


def load_metadata_records() -> list[dict[str, Any]]:
    if not METADATA_FILE or not os.path.exists(METADATA_FILE) or os.path.getsize(METADATA_FILE) == 0:
        return []
    with open(METADATA_FILE, "r", encoding="utf-8") as handle:
        records = json.load(handle)
    if not isinstance(records, list):
        raise ValueError("metadata.json phai chua mot JSON array.")
    return records


def configure_output_directory(input_file: str) -> None:
    global OUTPUT_DIR, METADATA_FILE, METADATA_BY_ITEM
    OUTPUT_DIR = os.path.dirname(os.path.abspath(input_file))
    METADATA_FILE = os.path.join(OUTPUT_DIR, "metadata.json")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    METADATA_BY_ITEM = {
        str(record["item_id"]): record for record in load_metadata_records() if record.get("item_id")
    }


def flush_metadata() -> None:
    """Write metadata once per completed batch instead of once per audio."""
    with METADATA_LOCK:
        records = sorted(METADATA_BY_ITEM.values(), key=lambda item: item.get("item_id", ""))
        atomic_write_json(METADATA_FILE, records)


def find_input_file(directory: str) -> str:
    candidates = sorted(
        os.path.join(directory, name) for name in os.listdir(directory)
        if re.fullmatch(r"sources_\d{4}(?:_\d{2})?\.json", name)
    )
    if not candidates:
        raise FileNotFoundError(f"Khong tim thay sources_DDMM.json trong: {directory}")
    if len(candidates) == 1:
        return candidates[0]
    print("Cac file input tim thay:")
    for index, candidate in enumerate(candidates, 1):
        print(f"  {index}. {os.path.basename(candidate)}")
    choice = input("Chon so file input: ").strip()
    if not choice.isdigit() or not 1 <= int(choice) <= len(candidates):
        raise ValueError("Lua chon file input khong hop le.")
    return candidates[int(choice) - 1]


def confirm_input(input_file: str) -> None:
    print(f"\nThu muc xu ly: {os.path.dirname(os.path.abspath(input_file))}")
    print(f"File input: {os.path.basename(input_file)}")
    print(f"So task: {len(load_tasks(input_file))}")
    if input("Bat dau xu ly file nay? [y/N]: ").strip().lower() not in {"y", "yes"}:
        raise RuntimeError("Da huy xu ly theo xac nhan cua nguoi dung.")


def safe_task_id(task_id: Any) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(task_id))


def run_media_command(command: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, capture_output=True, text=True, check=True, timeout=timeout)
    except subprocess.CalledProcessError as error:
        details = (error.stderr or error.stdout or "Khong co thong tin tu tien trinh.").strip()
        raise RuntimeError(f"Media command that bai (exit {error.returncode}): {details[-2000:]}") from error


def probe_wav(path: str) -> float:
    process = run_media_command([
        FFPROBE_PATH, "-v", "quiet", "-print_format", "json", "-show_streams", "-show_format", path,
    ], timeout=60)
    data = json.loads(process.stdout)
    stream = next((item for item in data.get("streams", []) if item.get("codec_type") == "audio"), None)
    if not stream:
        raise ValueError("Khong tim thay luong audio trong file dich.")
    if (str(stream.get("sample_rate")) != "16000" or int(stream.get("channels", 0)) != 1
            or stream.get("codec_name") != "pcm_s16le"):
        raise ValueError("Kiem dinh that bai: audio phai la WAV PCM_16, mono, 16 kHz.")
    duration = float(data.get("format", {}).get("duration") or 0)
    if duration <= 0:
        raise ValueError("Kiem dinh that bai: audio rong hoac khong co duration hop le.")
    return duration


def classify_error(message: str) -> tuple[str, bool]:
    message = message.lower()
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


def download_audio(url: str, task_id: str) -> str:
    """Retry network/extractor faults with backoff. Cookies are opt-in env configuration."""
    if yt_dlp is None:
        raise RuntimeError(f"Thieu yt-dlp. Cai bang: {sys.executable} -m pip install yt-dlp")
    attempts = max(1, int(os.getenv("YTDLP_DOWNLOAD_ATTEMPTS", "3")))
    cookie_file = os.getenv("YTDLP_COOKIEFILE")
    browser = os.getenv("YTDLP_COOKIES_FROM_BROWSER")
    proxy = os.getenv("YTDLP_PROXY")
    for attempt in range(1, attempts + 1):
        token = uuid.uuid4().hex
        options: dict[str, Any] = {
            "format": "bestaudio/best", "outtmpl": os.path.join(OUTPUT_DIR, f".download_{task_id}_{token}.%(ext)s"),
            "ffmpeg_location": CURRENT_DIR, "socket_timeout": 60, "retries": 1, "fragment_retries": 1,
            "quiet": True, "no_warnings": True,
        }
        if cookie_file:
            options["cookiefile"] = cookie_file
        if browser:
            options["cookiesfrombrowser"] = (browser,)
        if proxy is not None:
            options["proxy"] = proxy
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=True)
                downloaded = ydl.prepare_filename(info)
            if os.path.exists(downloaded):
                return downloaded
            raise FileNotFoundError("Tai file that bai, khong tim thay file tam.")
        except Exception as error:
            error_class, retryable = classify_error(str(error))
            if not retryable or attempt == attempts:
                raise RuntimeError(f"{error_class} after {attempt}/{attempts} attempts: {error}") from error
            delay = min(30.0, 2 ** (attempt - 1) + random.uniform(0, 1))
            print(f"  [Retry] {error_class}; thu lai sau {delay:.1f}s ({attempt}/{attempts}).")
            time.sleep(delay)
    raise RuntimeError("Download khong thanh cong.")


def build_audio_metadata(task: dict[str, Any], audio_path: str, duration: float,
                         source_duration: float, duration_mismatch: float | None) -> dict[str, Any]:
    video_id = str(task.get("platform_video_id") or "")
    if not video_id:
        match = re.search(r"/video/(\d+)", task.get("original_url", ""))
        video_id = match.group(1) if match else ""
    record = {
        "item_id": task.get("item_id") or f"tt_{video_id}", "platform": task.get("platform", "tiktok"),
        "platform_video_id": video_id, "video_url": task.get("original_url", ""), "title": task.get("title", ""),
        "description": task.get("description", ""), "posted_at": task.get("posted_at"),
        "language_raw": task.get("language_raw") or task.get("text_language", "unknown"),
        "audio_path": os.path.relpath(audio_path, CURRENT_DIR).replace(os.sep, "/"),
        "duration_seconds": round(duration, 2), "source_duration_seconds": round(source_duration, 2),
        "crawl_batch": task.get("crawl_batch", "tt_batch_01"),
        "crawled_at": task.get("crawled_at") or datetime.now(timezone.utc).isoformat(),
        "platform_meta": task.get("platform_meta", {}), "language_region": task.get("language_region", "mixed"),
        "enhancement_status": "success", "enhancement_model": "dpdfnet8.onnx",
    }
    if duration_mismatch is not None:
        record["duration_mismatch_seconds"] = round(duration_mismatch, 2)
    return record


def process_audio_task(task: dict[str, Any]) -> dict[str, Any]:
    task_id = safe_task_id(task.get("task_id", "UNKNOWN_ID"))
    result = {**task, "status": "failed", "error_message": "", "local_path": ""}
    final_file = os.path.join(OUTPUT_DIR, f"{task_id}.wav")
    token = uuid.uuid4().hex
    wav_temp = os.path.join(OUTPUT_DIR, f".{task_id}.{token}.wav.part")
    enhanced_temp = os.path.join(OUTPUT_DIR, f".{task_id}.{token}.enhanced.wav.part")
    downloaded: str | None = None
    existing = METADATA_BY_ITEM.get(str(task.get("item_id") or ""))
    if os.path.exists(final_file) and existing and existing.get("enhancement_status") == "success" and existing.get("enhancement_model") == "dpdfnet8.onnx":
        return {**result, "status": "success", "local_path": final_file, "metadata_path": METADATA_FILE, "resumed": True}
    try:
        if not isinstance(task.get("original_url"), str) or not task["original_url"]:
            raise ValueError("Task khong co original_url hop le.")
        if not os.path.isfile(FFMPEG_PATH) or not os.path.isfile(FFPROBE_PATH):
            raise FileNotFoundError("Khong tim thay ffmpeg.exe hoac ffprobe.exe.")
        if enhance_audio is None:
            raise RuntimeError(f"Thieu runtime DPDFNet. Cai bang: {sys.executable} -m pip install -r requirements.txt")
        print(f"\n[*] Task {task_id}: [1/5] tai audio")
        downloaded = download_audio(task["original_url"], task_id)
        print("  [2/5] chuan hoa 16kHz mono")
        run_media_command([FFMPEG_PATH, "-y", "-i", downloaded, "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", "-f", "wav", wav_temp], 300)
        print("  [3/5] kiem dinh audio dau vao")
        source_duration = probe_wav(wav_temp)
        mismatch = None
        if task.get("duration_seconds") is not None:
            mismatch = abs(source_duration - float(task["duration_seconds"]))
            if mismatch <= 2:
                mismatch = None
            else:
                print(f"  [Warning] Duration lech {mismatch:.2f}s; giu audio va ghi nhan metadata.")
        print("  [4/5] khu nhieu DPDFNet")
        enhance_audio(wav_temp, enhanced_temp)
        print("  [5/5] kiem dinh audio enhanced")
        enhanced_duration = probe_wav(enhanced_temp)
        os.replace(enhanced_temp, final_file)
        record = build_audio_metadata(task, final_file, enhanced_duration, source_duration, mismatch)
        with METADATA_LOCK:
            METADATA_BY_ITEM[str(record["item_id"])] = record
        result.update({"status": "success", "local_path": final_file, "metadata_path": METADATA_FILE,
                       "duration_mismatch_seconds": record.get("duration_mismatch_seconds")})
    except Exception as error:
        error_class, retryable = classify_error(str(error))
        result.update({"error_message": str(error), "error_class": error_class, "retryable": retryable})
        print(f"  [-] Task {task_id} ({error_class}): {error}")
    finally:
        for path in (downloaded, wav_temp, enhanced_temp):
            if path and os.path.exists(path):
                os.remove(path)
    return result


def write_run_report(input_file: str, results: list[dict[str, Any]]) -> str:
    failed = [item for item in results if item.get("status") != "success"]
    report = {
        "input_file": os.path.abspath(input_file), "finished_at": datetime.now(timezone.utc).isoformat(),
        "total": len(results), "success": len(results) - len(failed), "failed": len(failed),
        "error_classes": dict(Counter(item.get("error_class", "unknown") for item in failed)),
        "duration_mismatch_warnings": sum(bool(item.get("duration_mismatch_seconds")) for item in results),
    }
    path = os.path.join(OUTPUT_DIR, f"audio_processing_report_{os.path.splitext(os.path.basename(input_file))[0]}.json")
    atomic_write_json(path, report)
    return path


def run_batch(input_file: str, max_workers: int = 4) -> dict[str, Any]:
    tasks = load_tasks(input_file)
    worker_count = max(1, min(int(max_workers), 8))
    results: list[dict[str, Any]] = []
    print(f"[*] Bat dau batch: {len(tasks)} task, {worker_count} worker...")
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {executor.submit(process_audio_task, task): task for task in tasks}
        for done, future in enumerate(as_completed(futures), 1):
            task = futures[future]
            try:
                result = future.result()
            except Exception as error:
                error_class, _ = classify_error(str(error))
                result = {**task, "status": "failed", "error_message": str(error), "error_class": error_class}
            results.append(result)
            print(f"[*] Tien do {done}/{len(tasks)}: {result.get('task_id')} -> {result['status']}")
    flush_metadata()
    failed = [item for item in results if item.get("status") != "success"]
    failed_file = os.path.join(OUTPUT_DIR, "failed_tasks.json") if failed else ""
    if failed:
        atomic_write_json(failed_file, failed)
    return {"total": len(tasks), "success": len(tasks) - len(failed), "failed": len(failed),
            "failed_file": failed_file, "report_file": write_run_report(input_file, results)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Tai, chuan hoa, khu nhieu va kiem dinh audio theo batch.")
    parser.add_argument("--input", help="Duong dan file sources JSON.")
    parser.add_argument("--directory", default=CURRENT_DIR, help="Thu muc chua sources_DDMM.json.")
    parser.add_argument("--workers", type=int, default=4, help="So worker dong thoi, toi da 8.")
    parser.add_argument("--task-id", help="Chi xu ly mot task_id.")
    parser.add_argument("--yes", action="store_true", help="Bo qua xac nhan tuong tac; dung cho tu dong hoa.")
    parser.add_argument("--ignore-env-proxy", action="store_true", help="Bo qua HTTP(S)_PROXY/ALL_PROXY cua moi truong.")
    args = parser.parse_args()
    if args.ignore_env_proxy:
        for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
            os.environ.pop(name, None)
        os.environ["YTDLP_PROXY"] = ""
    input_file = os.path.abspath(args.input) if args.input else os.path.abspath(find_input_file(args.directory))
    if not os.path.isfile(input_file):
        raise FileNotFoundError(f"Khong tim thay file input: {input_file}")
    if not args.yes:
        confirm_input(input_file)
    configure_output_directory(input_file)
    if args.task_id:
        tasks = [task for task in load_tasks(input_file) if task.get("task_id") == args.task_id]
        if not tasks:
            raise ValueError(f"Khong tim thay task_id: {args.task_id}")
        result = process_audio_task(tasks[0])
        if result["status"] == "success":
            flush_metadata()
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return
    print(json.dumps(run_batch(input_file, args.workers), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, ValueError, json.JSONDecodeError, RuntimeError) as error:
        print(f"[-] {error}")
