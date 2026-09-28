"""Carrega config.json e resolve os caminhos do projeto."""

import copy
import json
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
BACKGROUNDS_PATH = ROOT / "backgrounds.json"

DEFAULTS: Dict[str, Any] = {
    "tts": {
        "voice": "pt-BR-AntonioNeural",
        "rate": "+8%",
        "pitch": "+0Hz",
        "volume": "+0%",
        "gap_seconds": 0.25,
        "concurrency": 3,
    },
    "video": {
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "encoder": "libx264",
        "preset": "medium",
        "crf": 23,
        "tail_seconds": 0.6,
    },
    "captions": {
        "enabled": True,
        "font": "Arial Black",
        "font_size": 76,
        "max_chars_per_line": 24,
        "max_lines": 2,
        "margin_v": 720,
        "primary_color": "&H00FFFFFF",
        "outline_color": "&H00000000",
        "outline": 6,
        "shadow": 2,
        "uppercase": False,
    },
    "background": {"choice": "minecraft", "music_file": "", "music_volume": 0.07},
    "text": {"min_chars": 60, "max_chars": 240},
    "paths": {
        "output_dir": "outputs",
        "temp_dir": "assets/temp",
        "backgrounds_dir": "assets/backgrounds/video",
    },
    "keep_temp": False,
}


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(overrides: dict | None = None) -> dict:
    """Config = DEFAULTS <- config.json <- overrides passados na chamada."""
    from_file = {}
    if CONFIG_PATH.is_file():
        from_file = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return _merge(_merge(DEFAULTS, from_file), overrides or {})


def save_config(config: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")


def load_backgrounds() -> Dict[str, list]:
    if not BACKGROUNDS_PATH.is_file():
        return {}
    data = json.loads(BACKGROUNDS_PATH.read_text(encoding="utf-8"))
    data.pop("__comment", None)
    return data


def path_from_config(config: dict, key: str) -> Path:
    """Caminhos do config sao relativos a raiz do projeto."""
    raw = Path(config["paths"][key])
    return raw if raw.is_absolute() else ROOT / raw
