"""Phân đoạn câu thoại (Utterance Segmentation) bằng Silero VAD v5 qua sherpa-onnx.

Quét file audio mono 16kHz, phát hiện các đoạn có tiếng người, cắt thành các
segment chuẩn ASR (2s - 15s), loại bỏ khoảng lặng và đoạn không có giọng nói.
"""

import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import sherpa_onnx
import soundfile as sf

MODEL_DIR = Path(__file__).resolve().parent
VAD_MODEL_PATH = MODEL_DIR / "silero_vad.onnx"
_vad_lock = threading.Lock()

# Ngưỡng cấu hình mặc định cho ASR corpus
DEFAULT_THRESHOLD = 0.45          # Ngưỡng xác suất phát hiện giọng nói
DEFAULT_MIN_SILENCE = 0.4         # Giây - khoảng lặng tối thiểu để cắt câu
DEFAULT_MIN_SPEECH = 0.5          # Giây - độ dài tối thiểu một đoạn nói
DEFAULT_MAX_SPEECH = 15.0         # Giây - độ dài tối đa cho 1 segment ASR
DEFAULT_MIN_SEGMENT = 2.0         # Giây - loại bỏ segment < 2s (quá ngắn cho ASR)


@dataclass
class SpeechSegment:
    """Đại diện 1 đoạn giọng nói đã cắt."""
    start_sample: int
    end_sample: int
    samples: np.ndarray
    sample_rate: int

    @property
    def start_seconds(self) -> float:
        return self.start_sample / self.sample_rate

    @property
    def end_seconds(self) -> float:
        return self.end_sample / self.sample_rate

    @property
    def duration(self) -> float:
        return len(self.samples) / self.sample_rate


def create_vad(
    model_path: str | Path = VAD_MODEL_PATH,
    threshold: float = DEFAULT_THRESHOLD,
    min_silence_duration: float = DEFAULT_MIN_SILENCE,
    min_speech_duration: float = DEFAULT_MIN_SPEECH,
    max_speech_duration: float = DEFAULT_MAX_SPEECH,
) -> sherpa_onnx.VoiceActivityDetector:
    """Khởi tạo Silero VAD detector."""
    model_path = Path(model_path).resolve()
    if not model_path.is_file():
        raise FileNotFoundError(f"Không tìm thấy Silero VAD model: {model_path}")

    config = sherpa_onnx.VadModelConfig(
        silero_vad=sherpa_onnx.SileroVadModelConfig(
            model=str(model_path),
            threshold=threshold,
            min_silence_duration=min_silence_duration,
            min_speech_duration=min_speech_duration,
            max_speech_duration=max_speech_duration,
        ),
        sample_rate=16000,
        num_threads=1,
        provider="cpu",
    )
    if not config.validate():
        raise ValueError(f"Cấu hình VAD không hợp lệ: {config}")
    return sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=120)


def _split_long_segment(
    seg: SpeechSegment,
    max_duration: float = DEFAULT_MAX_SPEECH,
    min_duration: float = DEFAULT_MIN_SEGMENT,
) -> list[SpeechSegment]:
    """Chia nhỏ một segment vượt quá max_duration (15s) tại các điểm năng lượng thấp nhất."""
    if seg.duration <= max_duration:
        return [seg]

    result: list[SpeechSegment] = []
    current_samples = seg.samples
    current_start = seg.start_sample
    sr = seg.sample_rate

    while len(current_samples) / sr > max_duration:
        target_sec = min(12.0, max_duration - 1.0)
        target_sample = int(target_sec * sr)
        search_start = max(int(min_duration * sr), target_sample - int(1.5 * sr))
        search_end = min(len(current_samples) - int(min_duration * sr), target_sample + int(1.5 * sr))

        if search_end > search_start:
            window = current_samples[search_start:search_end]
            frame_len = int(0.05 * sr)
            if len(window) > frame_len:
                energies = np.convolve(np.abs(window), np.ones(frame_len), mode="valid")
                cut_offset = search_start + int(np.argmin(energies)) + frame_len // 2
            else:
                cut_offset = target_sample
        else:
            cut_offset = target_sample

        sub_samples = current_samples[:cut_offset]
        result.append(SpeechSegment(
            start_sample=current_start,
            end_sample=current_start + len(sub_samples),
            samples=sub_samples,
            sample_rate=sr,
        ))
        current_samples = current_samples[cut_offset:]
        current_start += cut_offset

    if len(current_samples) / sr >= min_duration:
        result.append(SpeechSegment(
            start_sample=current_start,
            end_sample=current_start + len(current_samples),
            samples=current_samples,
            sample_rate=sr,
        ))

    return result


def detect_speech_segments(
    audio_path: str | Path,
    min_segment_duration: float = DEFAULT_MIN_SEGMENT,
    threshold: float = DEFAULT_THRESHOLD,
    min_silence_duration: float = DEFAULT_MIN_SILENCE,
    min_speech_duration: float = DEFAULT_MIN_SPEECH,
    max_speech_duration: float = DEFAULT_MAX_SPEECH,
) -> list[SpeechSegment]:
    """Phát hiện và trả về danh sách các đoạn giọng nói từ file audio.

    Args:
        audio_path: Đường dẫn file WAV mono 16kHz.
        min_segment_duration: Loại bỏ segment ngắn hơn giá trị này (giây).
        threshold: Ngưỡng xác suất VAD (0-1).
        min_silence_duration: Khoảng lặng tối thiểu để tách câu (giây).
        min_speech_duration: Độ dài tối thiểu một đoạn phát ngôn (giây).
        max_speech_duration: Độ dài tối đa một segment (giây).

    Returns:
        Danh sách SpeechSegment đã sắp xếp theo thứ tự thời gian.
    """
    samples, sample_rate = sf.read(str(audio_path), always_2d=True, dtype="float32")
    if sample_rate != 16000:
        raise ValueError(f"Audio phải có sample rate 16000 Hz, nhận được {sample_rate} Hz")
    if samples.shape[1] != 1:
        raise ValueError(f"Audio phải là mono, nhận được {samples.shape[1]} channels")
    mono = np.ascontiguousarray(samples[:, 0])

    vad = create_vad(
        threshold=threshold,
        min_silence_duration=min_silence_duration,
        min_speech_duration=min_speech_duration,
        max_speech_duration=max_speech_duration,
    )

    window_size = vad.config.silero_vad.window_size
    segments: list[SpeechSegment] = []

    # Đưa audio vào VAD theo từng cửa sổ
    offset = 0
    while offset + window_size <= len(mono):
        chunk = mono[offset: offset + window_size].tolist()
        vad.accept_waveform(chunk)
        offset += window_size

    # Flush phần đuôi còn lại
    vad.flush()

    # Thu thập tất cả segments đã phát hiện
    while not vad.empty():
        seg = vad.front
        seg_samples = np.array(seg.samples, dtype=np.float32)
        duration = len(seg_samples) / sample_rate

        if duration >= min_segment_duration:
            base_seg = SpeechSegment(
                start_sample=seg.start,
                end_sample=seg.start + len(seg_samples),
                samples=seg_samples,
                sample_rate=sample_rate,
            )
            split_segs = _split_long_segment(
                base_seg,
                max_duration=max_speech_duration,
                min_duration=min_segment_duration,
            )
            segments.extend(split_segs)
        vad.pop()

    return segments


def slice_and_save(
    audio_path: str | Path,
    output_dir: str | Path,
    task_id: str,
    min_segment_duration: float = DEFAULT_MIN_SEGMENT,
) -> list[dict]:
    """Cắt audio thành các segment và lưu file WAV (PCM 16-bit 16kHz mono).

    Args:
        audio_path: Đường dẫn file WAV mono 16kHz đã xử lý (vocals + denoised).
        output_dir: Thư mục lưu các file segment.
        task_id: ID của task gốc (ví dụ: "ID_0001").
        min_segment_duration: Loại bỏ segment ngắn hơn giá trị này.

    Returns:
        Danh sách dict chứa thông tin từng segment đã lưu:
        [{"filename": "ID_0001_seg001.wav", "duration": 7.42, "start": 1.2, "end": 8.62}, ...]
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    segments = detect_speech_segments(audio_path, min_segment_duration=min_segment_duration)
    saved = []

    for index, segment in enumerate(segments, start=1):
        filename = f"{task_id}_seg{index:03d}.wav"
        filepath = output_dir / filename

        sf.write(
            str(filepath),
            segment.samples,
            segment.sample_rate,
            format="WAV",
            subtype="PCM_16",
        )

        saved.append({
            "filename": filename,
            "duration": round(segment.duration, 2),
            "start": round(segment.start_seconds, 3),
            "end": round(segment.end_seconds, 3),
        })

    return saved
