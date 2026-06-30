from __future__ import annotations

import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from backend.app.core.config import MODEL_SETTINGS_DEFAULTS, MODEL_SETTINGS_PATH

_SETTING_KEYS = ("OPENAI_API_KEY", "OPENAI_BASE_URL", "LLM_MODEL", "QA_QUALITY_EVALUATOR")


def _normalize_settings(data: dict[str, Any] | None) -> dict[str, str]:
    source = data or {}
    settings = {
        key: str(source.get(key, MODEL_SETTINGS_DEFAULTS[key]) or "").strip()
        for key in _SETTING_KEYS
    }
    if not settings["OPENAI_BASE_URL"]:
        settings["OPENAI_BASE_URL"] = MODEL_SETTINGS_DEFAULTS["OPENAI_BASE_URL"]
    if not settings["LLM_MODEL"]:
        settings["LLM_MODEL"] = MODEL_SETTINGS_DEFAULTS["LLM_MODEL"]
    if not settings["QA_QUALITY_EVALUATOR"]:
        settings["QA_QUALITY_EVALUATOR"] = MODEL_SETTINGS_DEFAULTS["QA_QUALITY_EVALUATOR"]
    return settings


def _load_settings(path: Path) -> dict[str, str]:
    if not path.exists():
        return _normalize_settings(None)

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return _normalize_settings(None)

    if not isinstance(payload, dict):
        return _normalize_settings(None)
    return _normalize_settings(payload)


def _write_settings(path: Path, settings: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent) as temp:
        json.dump(settings, temp, ensure_ascii=False, indent=2)
        temp.write("\n")
        temp_path = Path(temp.name)
    temp_path.replace(path)


def initialize_model_settings() -> dict[str, str]:
    settings = _load_settings(MODEL_SETTINGS_PATH)
    _write_settings(MODEL_SETTINGS_PATH, settings)
    return settings


def get_model_settings() -> dict[str, str]:
    return _load_settings(MODEL_SETTINGS_PATH)


def update_model_settings(settings: dict[str, Any]) -> dict[str, str]:
    current = _load_settings(MODEL_SETTINGS_PATH)
    merged = {**current, **(settings or {})}
    normalized = _normalize_settings(merged)
    _write_settings(MODEL_SETTINGS_PATH, normalized)
    return normalized
