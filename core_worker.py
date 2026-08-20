import os
import json
import subprocess
import re
import argparse
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

try:
    import yt_dlp
except ModuleNotFoundError:
    yt_dlp = None

# 1. THIẾT LẬP ĐƯỜNG DẪN PORTABLE
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
FFMPEG_PATH = os.path.join(CURRENT_DIR, "ffmpeg.exe")
FFPROBE_PATH = os.path.join(CURRENT_DIR, "ffprobe.exe")
OUTPUT_DIR = os.path.join(CURRENT_DIR, "WEEK1_2008")
METADATA_FILE = os.path.join(OUTPUT_DIR, "metadata.json")
os.makedirs(OUTPUT_DIR, exist_ok=True)
METADATA_LOCK = threading.Lock()


def safe_task_id(task_id: Any) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(task_id))


def build_audio_metadata(task: dict[str, Any], audio_path: str, duration: float) -> dict[str, Any]:
    """Tạo record metadata theo format chuẩn cho một audio đã kiểm định."""
    task_id = safe_task_id(task.get("task_id", "UNKNOWN_ID"))
    video_id = str(task.get("platform_video_id") or "")
    if not video_id:
        match = re.search(r"/video/(\d+)", task.get("original_url", ""))
        video_id = match.group(1) if match else ""

    return {
        "item_id": task.get("item_id") or f"tt_{video_id}",
        "platform": task.get("platform", "tiktok"),
        "platform_video_id": video_id,
        "video_url": task.get("original_url", ""),
        "title": task.get("title", ""),
        "description": task.get("description", ""),
        "posted_at": task.get("posted_at"),
        "language_raw": task.get("language_raw") or task.get("text_language", "unknown"),
        "audio_path": os.path.relpath(audio_path, CURRENT_DIR).replace(os.sep, "/"),
        "duration_seconds": round(duration, 2),
        "crawl_batch": task.get("crawl_batch", "tt_batch_01"),
        "crawled_at": task.get("crawled_at") or datetime.now(timezone.utc).isoformat(),
        "platform_meta": task.get("platform_meta", {
            "music_is_original": False,
            "is_duet": False,
            "is_stitch": False,
            "has_platform_captions": False
        }),
        "language_region": task.get("language_region", "mixed")
    }


def load_metadata_records() -> list[dict[str, Any]]:
    if not os.path.exists(METADATA_FILE) or os.path.getsize(METADATA_FILE) == 0:
        return []

    with open(METADATA_FILE, "r", encoding="utf-8") as metadata_handle:
        records = json.load(metadata_handle)

    if not isinstance(records, list):
        raise ValueError("metadata.json phải chứa một JSON array.")
    return records


def upsert_metadata_record(record: dict[str, Any]) -> None:
    """Thêm hoặc cập nhật record theo item_id, ghi file theo cách an toàn."""
    with METADATA_LOCK:
        records = load_metadata_records()
        records = [
            existing for existing in records
            if existing.get("item_id") != record.get("item_id")
        ]
        records.append(record)
        records.sort(key=lambda item: item.get("item_id", ""))

        metadata_temp_file = f"{METADATA_FILE}.part"
        with open(metadata_temp_file, "w", encoding="utf-8") as metadata_handle:
            json.dump(records, metadata_handle, ensure_ascii=False, indent=2)
            metadata_handle.write("\n")
        os.replace(metadata_temp_file, METADATA_FILE)


def load_tasks(input_file: str) -> list[dict[str, Any]]:
    with open(input_file, "r", encoding="utf-8") as input_handle:
        tasks = json.load(input_handle)

    if not isinstance(tasks, list):
        raise ValueError("sources.json phải chứa một JSON array.")
    return tasks


def write_failed_tasks(failed_tasks: list[dict[str, Any]]) -> str:
    failed_file = os.path.join(OUTPUT_DIR, "failed_tasks.json")
    temp_file = f"{failed_file}.part"
    with open(temp_file, "w", encoding="utf-8") as failed_handle:
        json.dump(failed_tasks, failed_handle, ensure_ascii=False, indent=2)
        failed_handle.write("\n")
    os.replace(temp_file, failed_file)
    return failed_file


def run_media_command(command: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    """Chạy FFmpeg/FFprobe và giữ lại stderr khi tiến trình thất bại."""
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout
        )
    except subprocess.CalledProcessError as error:
        details = (error.stderr or error.stdout or "Không có thông tin từ tiến trình.").strip()
        raise RuntimeError(
            f"Media command thất bại (exit {error.returncode}): {details[-2000:]}"
        ) from error


def run_batch(input_file: str, max_workers: int = 4) -> dict[str, Any]:
    """Xử lý batch có giới hạn worker và tiếp tục khi một task thất bại."""
    tasks = load_tasks(input_file)
    results = []

    worker_count = max(1, min(int(max_workers), 8))
    print(f"[*] Bắt đầu batch: {len(tasks)} task, {worker_count} worker...")

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(process_audio_task, task): task
            for task in tasks
        }
        for completed_count, future in enumerate(as_completed(futures), start=1):
            task = futures[future]
            try:
                result = future.result()
            except Exception as error:
                result = task.copy()
                result.update({
                    "status": "failed",
                    "error_message": str(error),
                    "local_path": "",
                    "metadata_path": METADATA_FILE
                })
            results.append(result)
            print(
                f"[*] Tiến độ {completed_count}/{len(tasks)}: "
                f"{result.get('task_id', 'UNKNOWN_ID')} -> {result.get('status')}"
            )

    failed_tasks = [result for result in results if result.get("status") != "success"]
    summary = {
        "total": len(tasks),
        "success": len(tasks) - len(failed_tasks),
        "failed": len(failed_tasks),
        "failed_file": write_failed_tasks(failed_tasks) if failed_tasks else ""
    }
    print(
        f"[+] Hoàn tất: {summary['success']} thành công, "
        f"{summary['failed']} thất bại."
    )
    return summary

def process_audio_task(task: dict[str, Any]) -> dict[str, Any]:
    """
    Hàm xử lý toàn bộ vòng đời của 1 URL: Tải -> Convert -> Kiểm định -> Dọn dẹp
    """
    task_id = safe_task_id(task.get("task_id", "UNKNOWN_ID"))
    url = task.get("original_url")
    
    print(f"\n[*] Đang xử lý Task: {task_id} | URL: {url}")
    
    # Kết quả trả về mặc định
    result = task.copy()
    result["status"] = "failed"
    result["error_message"] = ""
    result["local_path"] = ""
    
    temp_downloaded_file = None
    final_wav_file = os.path.join(OUTPUT_DIR, f"{task_id}.wav")
    wav_temp_file = os.path.join(OUTPUT_DIR, f".{task_id}.wav.part")
    metadata_temp_file = os.path.join(OUTPUT_DIR, f".{task_id}.json.part")
    metadata_file = METADATA_FILE

    existing_metadata = []
    if os.path.exists(metadata_file) and os.path.getsize(metadata_file) > 0:
        existing_metadata = load_metadata_records()
    item_id = task.get("item_id")
    has_metadata = any(record.get("item_id") == item_id for record in existing_metadata)

    if os.path.exists(final_wav_file) and has_metadata:
        result["status"] = "success"
        result["local_path"] = final_wav_file
        result["metadata_path"] = metadata_file
        return result
    
    try:
        if yt_dlp is None:
            raise RuntimeError("Thiếu thư viện yt-dlp. Cài bằng: python -m pip install yt-dlp")
        if not url or not isinstance(url, str):
            raise ValueError("Task không có original_url hợp lệ.")
        if not os.path.isfile(FFMPEG_PATH):
            raise FileNotFoundError(f"Không tìm thấy FFmpeg: {FFMPEG_PATH}")
        if not os.path.isfile(FFPROBE_PATH):
            raise FileNotFoundError(f"Không tìm thấy FFprobe: {FFPROBE_PATH}")

        # ==========================================
        # BƯỚC 1: TẢI AUDIO BẰNG YT-DLP
        # ==========================================
        print(f"  [1/3] Đang tải audio bằng yt-dlp...")
        ydl_opts = {
            'format': 'bestaudio/best', # Chỉ tải luồng audio tốt nhất
            'outtmpl': os.path.join(CURRENT_DIR, f'temp_{task_id}.%(ext)s'),
            'ffmpeg_location': CURRENT_DIR, # Trỏ đến ffmpeg cục bộ
            'socket_timeout': 60,
            'retries': 3,
            'fragment_retries': 3,
            'quiet': True,
            'no_warnings': True
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # extract_info để tải, sau đó lấy thông tin file thực tế vừa lưu
            info = ydl.extract_info(url, download=True)
            temp_downloaded_file = ydl.prepare_filename(info)
            
        if not os.path.exists(temp_downloaded_file):
            raise FileNotFoundError("Tải file thất bại, không tìm thấy file tạm.")

        # ==========================================
        # BƯỚC 2: CHUẨN HÓA BẰNG FFMPEG (WAV, 16kHz, MONO)
        # ==========================================
        print(f"  [2/3] Đang chuẩn hóa (16kHz, mono) bằng ffmpeg...")
        convert_cmd = [
            FFMPEG_PATH, 
            "-y", # Ghi đè nếu đã tồn tại file trùng tên
            "-i", temp_downloaded_file,
            "-ac", "1",               # Channel: Mono
            "-ar", "16000",           # Sample rate: 16 kHz
            "-c:a", "pcm_s16le",      # Định dạng chuẩn PCM 16-bit
            "-f", "wav",               # Ép định dạng vì file tạm kết thúc bằng .part
            wav_temp_file
        ]
        
        # Chạy lệnh ffmpeg (chặn luồng text in ra màn hình để tránh nhiễu)
        run_media_command(convert_cmd, timeout=300)

        # ==========================================
        # BƯỚC 3: KIỂM ĐỊNH BẰNG FFPROBE
        # ==========================================
        print(f"  [3/3] Đang xác minh thông số kỹ thuật bằng ffprobe...")
        probe_cmd = [
            FFPROBE_PATH, 
            "-v", "quiet", 
            "-print_format", "json",
            "-show_streams", 
            "-show_format",
            wav_temp_file
        ]
        
        probe_process = run_media_command(probe_cmd, timeout=60)
        probe_data = json.loads(probe_process.stdout)
        
        # Tìm luồng audio trong dữ liệu ffprobe trả về
        audio_stream = next((stream for stream in probe_data.get('streams', []) if stream['codec_type'] == 'audio'), None)
        
        if not audio_stream:
            raise ValueError("Không tìm thấy luồng audio trong file đích.")
            
        # Xác minh chéo 3 thông số bắt buộc (Assert)
        actual_sample_rate = str(audio_stream.get('sample_rate'))
        actual_channels = int(audio_stream.get('channels', 0))
        actual_codec = audio_stream.get('codec_name')
        actual_duration = float(probe_data.get("format", {}).get("duration") or 0)
        
        if actual_sample_rate != "16000" or actual_channels != 1 or actual_codec != "pcm_s16le":
            raise ValueError(f"Kiểm định thất bại! SR: {actual_sample_rate}, CH: {actual_channels}, Codec: {actual_codec}")

        expected_duration = task.get("duration_seconds")
        if expected_duration is not None and abs(actual_duration - float(expected_duration)) > 2:
            raise ValueError("Thời lượng audio sau chuyển đổi không khớp metadata đầu vào.")

        os.replace(wav_temp_file, final_wav_file)
        metadata = build_audio_metadata(task, final_wav_file, actual_duration)
        upsert_metadata_record(metadata)

        # ==========================================
        # BƯỚC 4: CẬP NHẬT KẾT QUẢ THÀNH CÔNG
        # ==========================================
        print(f"  [+] Thành công! File đạt chuẩn lưu tại: {final_wav_file}")
        result["status"] = "success"
        result["local_path"] = final_wav_file
        result["metadata_path"] = metadata_file
        
    except Exception as e:
        # Nếu có bất kỳ lỗi gì ở 3 bước trên, nhảy vào đây
        error_msg = str(e)
        print(f"  [-] Lỗi tại Task {task_id}: {error_msg}")
        result["error_message"] = error_msg
        
        # Nếu đã lỡ tạo ra file final_wav bị lỗi, xóa nó đi
        if os.path.exists(final_wav_file):
            os.remove(final_wav_file)
        if os.path.exists(wav_temp_file):
            os.remove(wav_temp_file)
        if os.path.exists(metadata_temp_file):
            os.remove(metadata_temp_file)
            
    finally:
        # ==========================================
        # DỌN DẸP FILE RÁC (Luôn luôn thực thi)
        # ==========================================
        if temp_downloaded_file and os.path.exists(temp_downloaded_file):
            os.remove(temp_downloaded_file)
            print(f"  [Cleanup] Đã xóa file tạm gốc.")
            
    return result

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tai, chuan hoa va kiem dinh audio TikTok theo batch."
    )
    parser.add_argument(
        "--input",
        default=os.path.join(CURRENT_DIR, "sources.json"),
        help="Duong dan file JSON chua danh sach task."
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="So worker dong thoi, toi da 8."
    )
    parser.add_argument(
        "--task-id",
        help="Chi xu ly mot task_id, bo qua de xu ly ca batch."
    )
    args = parser.parse_args()

    if not os.path.isfile(args.input):
        raise FileNotFoundError(f"Khong tim thay file input: {args.input}")

    if args.task_id:
        tasks = [
            task for task in load_tasks(args.input)
            if task.get("task_id") == args.task_id
        ]
        if not tasks:
            raise ValueError(f"Khong tim thay task_id: {args.task_id}")
        result = process_audio_task(tasks[0])
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    run_batch(args.input, args.workers)


if __name__ == "__main__":
    main()