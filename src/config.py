"""Configuration loader for TikTok Data Pipeline."""

import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional
import yaml
from dotenv import load_dotenv

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace", line_buffering=True)
    except Exception:
        pass

if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace", line_buffering=True)
    except Exception:
        pass

# Load .env file automatically
load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "settings.yaml"

_CONFIG_CACHE: Optional[Dict[str, Any]] = None


def load_config(config_path: Optional[str | Path] = None) -> Dict[str, Any]:
    """Load configuration from YAML file, with environment variable overrides."""
    global _CONFIG_CACHE
    path = Path(config_path or os.getenv("CONFIG_PATH") or DEFAULT_CONFIG_PATH)

    if not path.is_file():
        path = DEFAULT_CONFIG_PATH

    if path.is_file():
        with open(path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    else:
        config = {}

    config.setdefault("paths", {})
    config.setdefault("crawler", {})
    config.setdefault("media", {})
    config.setdefault("media", {}).setdefault("download", {})
    config.setdefault("media", {}).setdefault("models", {})

    if os.getenv("YTDLP_DOWNLOAD_ATTEMPTS"):
        config["media"]["download"]["attempts"] = int(os.environ["YTDLP_DOWNLOAD_ATTEMPTS"])
    if os.getenv("YTDLP_PROXY"):
        config["media"]["download"]["proxy"] = os.environ["YTDLP_PROXY"]
    if os.getenv("YTDLP_COOKIEFILE"):
        config["media"]["download"]["cookiefile"] = os.environ["YTDLP_COOKIEFILE"]
    if os.getenv("YTDLP_COOKIES_FROM_BROWSER"):
        config["media"]["download"]["cookies_from_browser"] = os.environ["YTDLP_COOKIES_FROM_BROWSER"]

    if os.getenv("UVR_NUM_THREADS"):
        config["media"]["models"]["uvr_num_threads"] = int(os.environ["UVR_NUM_THREADS"])
    if os.getenv("DPDFNET_NUM_THREADS"):
        config["media"]["models"]["dpdfnet_num_threads"] = int(os.environ["DPDFNET_NUM_THREADS"])
    if os.getenv("SHERPA_ONNX_PROVIDER"):
        config["media"]["models"]["sherpa_provider"] = os.environ["SHERPA_ONNX_PROVIDER"]

    _CONFIG_CACHE = config
    return config


def get_config() -> Dict[str, Any]:
    """Return cached configuration or load default."""
    global _CONFIG_CACHE
    if _CONFIG_CACHE is None:
        _CONFIG_CACHE = load_config()
    return _CONFIG_CACHE


def get_project_root() -> Path:
    """Return the absolute Path to project root."""
    return PROJECT_ROOT


def resolve_path(rel_or_abs: str | Path) -> Path:
    """Resolve a relative path against PROJECT_ROOT, or return absolute path."""
    path = Path(rel_or_abs)
    if path.is_absolute():
        return path
    return (PROJECT_ROOT / path).resolve()
