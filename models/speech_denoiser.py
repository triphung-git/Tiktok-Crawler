import argparse
import threading
from pathlib import Path
import numpy as np
import sherpa_onnx
import soundfile as sf


PROJECT_DIR = Path(__file__).resolve().parent.parent
MODEL_PATH = Path(__file__).resolve().parent / "dpdfnet8.onnx"
_denoiser_local = threading.local()


def load_audio(filename: str | Path) -> tuple[np.ndarray, int]:
    samples, sample_rate = sf.read(
        str(filename),
        always_2d=True,
        dtype="float32",
    )
    if samples.shape[1] != 1:
        raise ValueError(f"Audio phải là mono, nhận được {samples.shape[1]} channels")
    if sample_rate != 16000:
        raise ValueError(f"Audio phải có sample rate 16000 Hz, nhận được {sample_rate} Hz")
    return np.ascontiguousarray(samples[:, 0]), sample_rate


def create_denoiser(model_path: str | Path = MODEL_PATH) -> sherpa_onnx.OfflineSpeechDenoiser:
    model_path = Path(model_path).resolve()
    if not model_path.is_file():
        raise FileNotFoundError(f"Không tìm thấy DPDFNet model: {model_path}")

    config = sherpa_onnx.OfflineSpeechDenoiserConfig(
        model=sherpa_onnx.OfflineSpeechDenoiserModelConfig(
            dpdfnet=sherpa_onnx.OfflineSpeechDenoiserDpdfNetModelConfig(
                model=str(model_path),
                attenuation_limit_db=12.0,
            ),
            num_threads=1,
            debug=False,
            provider="cpu",
        )
    )
    if not config.validate():
        raise ValueError(f"Cấu hình DPDFNet không hợp lệ: {config}")
    return sherpa_onnx.OfflineSpeechDenoiser(config)


def get_denoiser() -> sherpa_onnx.OfflineSpeechDenoiser:
    denoiser = getattr(_denoiser_local, "instance", None)
    if denoiser is None:
        denoiser = create_denoiser()
        _denoiser_local.instance = denoiser
    return denoiser


def enhance_audio(input_path: str | Path, output_path: str | Path) -> None:
    samples, sample_rate = load_audio(input_path)
    denoised = get_denoiser().run(samples, sample_rate)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(
        str(output_path),
        denoised.samples,
        denoised.sample_rate,
        format="WAV",
        subtype="PCM_16",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Enhance mono 16 kHz WAV with DPDFNet.")
    parser.add_argument("input", type=Path, help="Input WAV file")
    parser.add_argument("output", type=Path, help="Enhanced output WAV file")
    args = parser.parse_args()
    enhance_audio(args.input, args.output)
    print(f"Saved to {args.output.resolve()}")


if __name__ == "__main__":
    main()