"""Audio downloader using yt-dlp with exponential backoff and error classification."""

import os
import random
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

try:
    import yt_dlp
except ModuleNotFoundError:
    yt_dlp = None

from src.config import get_config, resolve_path
from src.processing.validator import classify_error


class AudioDownloader:
    """Tải audio từ TikTok / YouTube / Facebook bằng yt-dlp với cơ chế retry thông minh."""

    def __init__(self, options: Optional[Dict[str, Any]] = None):
        config = get_config()
        download_cfg = config.get("media", {}).get("download", {})
        self.attempts = max(1, int(download_cfg.get("attempts", 3)))
        self.cookie_file = download_cfg.get("cookiefile")
        self.browser = download_cfg.get("cookies_from_browser")
        self.proxy = download_cfg.get("proxy")
        self.socket_timeout = int(download_cfg.get("socket_timeout", 60))
        self.extra_options = options or {}

    def download(self, url: str, output_dir: str | Path, task_id: str) -> str:
        """
        Tải audio về thư mục output_dir. Trả về đường dẫn file đã tải.
        Tự động retry khi gặp sự cố mạng hoặc rate-limit.
        """
        if yt_dlp is None:
            raise RuntimeError(f"Thiếu yt-dlp. Cài bằng: {sys.executable} -m pip install yt-dlp")

        out_path = Path(output_dir).resolve()
        out_path.mkdir(parents=True, exist_ok=True)

        for attempt in range(1, self.attempts + 1):
            token = uuid.uuid4().hex
            template = str(out_path / f".download_{task_id}_{token}.%(ext)s")

            ydl_opts: Dict[str, Any] = {
                "format": "bestaudio/best",
                "outtmpl": template,
                "socket_timeout": self.socket_timeout,
                "retries": 1,
                "fragment_retries": 1,
                "quiet": True,
                "no_warnings": True,
            }

            if self.cookie_file:
                ydl_opts["cookiefile"] = self.cookie_file
            if self.browser:
                ydl_opts["cookiesfrombrowser"] = (self.browser,)
            if self.proxy:
                ydl_opts["proxy"] = self.proxy

            ydl_opts.update(self.extra_options)

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    downloaded = ydl.prepare_filename(info)

                if os.path.exists(downloaded):
                    return downloaded
                raise FileNotFoundError("Tải file thất bại, không tìm thấy file tạm trên đĩa.")

            except Exception as error:
                error_class, retryable = classify_error(str(error))
                if not retryable or attempt == self.attempts:
                    raise RuntimeError(f"{error_class} after {attempt}/{self.attempts} attempts: {error}") from error

                delay = min(30.0, 2 ** (attempt - 1) + random.uniform(0, 1))
                print(f"  [Retry] {error_class}; thử lại sau {delay:.1f}s ({attempt}/{self.attempts}).")
                time.sleep(delay)

        raise RuntimeError("Download không thành công sau tất cả các lần thử.")


def download_audio(url: str, output_dir: str | Path, task_id: str) -> str:
    """Helper tiện ích gọi nhanh AudioDownloader."""
    downloader = AudioDownloader()
    return downloader.download(url, output_dir, task_id)
