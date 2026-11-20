"""config/settings.yaml을 읽는다. 환경 변수가 있으면 yaml 값보다 우선한다 (docs/spec/config.md)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "config" / "settings.yaml"

# 환경 변수 → settings 키
ENV_OVERRIDES = {
    "GATEWAY_PORT": ("serial", "gateway_port"),
    "ARDUINO_PORT": ("serial", "arduino_port"),
    "MQTT_HOST": ("mqtt", "host"),
    "MQTT_PORT": ("mqtt", "port"),
}


def load_settings(path: str | Path | None = None) -> dict[str, Any]:
    with open(path or DEFAULT_PATH, encoding="utf-8") as f:
        settings = yaml.safe_load(f) or {}
    for env, (section, key) in ENV_OVERRIDES.items():
        value = os.environ.get(env)
        if value:
            settings.setdefault(section, {})[key] = int(value) if key == "port" else value
    return settings
