"""Tách nhạc nền (Music-Vocal Separation) bằng UVR MDX-Net qua sherpa-onnx.

Nhận file WAV mono 16kHz, resample lên 44.1kHz stereo cho UVR xử lý,
sau đó chuyển kết quả vocals về mono 16kHz phục vụ pipeline ASR.
"""

import os
import threading
from pathlib import Path

import numpy as np
import sherpa_onnx
import soundfile as sf

MODEL_DIR = Path(__file__).resolve().parent
UVR_MODEL_PATH = MODEL_DIR / "UVR-MDX-NET-Voc_FT.onnx"
_separator_local = threading.local()


import math
try:
    import scipy.signal as sps
except ImportError:
    sps = None


def _resample_audio(samples: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """Resample audio chất lượng cao bằng polyphase filter chống aliasing."""
    if orig_sr == target_sr or len(samples) == 0:
        return samples
    if sps is not None:
        gcd = math.gcd(orig_sr, target_sr)
        up = target_sr // gcd
        down = orig_sr // gcd
        return sps.resample_poly(samples, up, down).astype(np.float32)

    # Fallback nội suy tuyến tính nếu không có scipy
    ratio = target_sr / orig_sr
    new_length = int(len(samples) * ratio)
    indices = np.arange(new_length) / ratio
    left = np.floor(indices).astype(np.int64)
    right = np.minimum(left + 1, len(samples) - 1)
    frac = (indices - left).astype(np.float32)
    return (samples[left] * (1 - frac) + samples[right] * frac).astype(np.float32)


def create_separator(model_path: str | Path = UVR_MODEL_PATH) -> sherpa_onnx.OfflineSourceSeparation:
    """Khởi tạo UVR MDX-Net separator."""
    model_path = Path(model_path).resolve()
    if not model_path.is_file():
        raise FileNotFoundError(f"Không tìm thấy UVR model: {model_path}")

    # Tối ưu hóa số luồng CPU: CPU đa nhân (như Intel i5 12 nhân) cho hiệu năng tốt nhất ở 6-8 threads
    num_threads = max(1, int(os.getenv("UVR_NUM_THREADS", min(8, os.cpu_count() or 1))))
    provider = os.getenv("SHERPA_ONNX_PROVIDER", "cpu").lower()

    config = sherpa_onnx.OfflineSourceSeparationConfig(
        model=sherpa_onnx.OfflineSourceSeparationModelConfig(
            uvr=sherpa_onnx.OfflineSourceSeparationUvrModelConfig(
                model=str(model_path),
            ),
            num_threads=num_threads,
            debug=False,
            provider=provider,
        )
    )
    if not config.validate():
        # Fallback về cpu nếu provider yêu cầu không hợp lệ
        if provider != "cpu":
            config.model.provider = "cpu"
        if not config.validate():
            raise ValueError(f"Cấu hình UVR không hợp lệ: {config}")
    return sherpa_onnx.OfflineSourceSeparation(config)


def get_separator() -> sherpa_onnx.OfflineSourceSeparation:
    """Thread-local singleton cho UVR separator."""
    sep = getattr(_separator_local, "instance", None)
    if sep is None:
        sep = create_separator()
        _separator_local.instance = sep
    return sep


def separate_vocals(input_path: str | Path, output_path: str | Path) -> None:
    """Tách vocals từ audio, xuất file WAV mono 16kHz chỉ chứa giọng nói.

    Quy trình:
    1. Đọc file mono 16kHz (chuẩn từ ffmpeg pipeline).
    2. Resample lên 44100Hz stereo (2 kênh giống nhau) — UVR yêu cầu.
    3. Chạy UVR separation → lấy track vocals.
    4. Chuyển vocals về mono 16kHz, lưu WAV PCM_16.
    """
    samples, sample_rate = sf.read(str(input_path), always_2d=True, dtype="float32")
    if samples.shape[1] != 1:
        raise ValueError(f"Audio phải là mono, nhận được {samples.shape[1]} channels")
    mono = np.ascontiguousarray(samples[:, 0])

    # Resample lên 44100Hz cho UVR
    target_sr = 44100
    resampled = _resample_audio(mono, sample_rate, target_sr)

    # Tạo stereo (2 kênh giống nhau) — UVR cần shape (num_channels, num_samples)
    stereo = np.stack([resampled, resampled], axis=0).astype(np.float32)

    # Chạy UVR separation
    separator = get_separator()
    result = separator.process(target_sr, stereo)

    # Lấy track vocals (thường là stem đầu tiên), chuyển về mono
    # result chứa danh sách stems; UVR Voc_FT: stem[0]=vocals, stem[1]=accompaniment
    vocals_stereo = np.array(result.stems[0].data, dtype=np.float32)
    del result, samples, mono, resampled, stereo

    if vocals_stereo.ndim == 2:
        vocals_mono = vocals_stereo.mean(axis=0)
    else:
        vocals_mono = vocals_stereo
    del vocals_stereo

    # Resample vocals về 16kHz
    vocals_16k = _resample_audio(vocals_mono, target_sr, 16000)
    del vocals_mono

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output_path), vocals_16k, 16000, format="WAV", subtype="PCM_16")
    del vocals_16k
