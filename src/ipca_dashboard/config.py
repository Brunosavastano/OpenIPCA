from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"


@dataclass(frozen=True)
class ProjectPaths:
    root: Path = PROJECT_ROOT
    config: Path = CONFIG_DIR
    raw: Path = RAW_DIR
    processed: Path = PROCESSED_DIR
    outputs: Path = OUTPUTS_DIR


def ensure_project_dirs() -> None:
    for path in [RAW_DIR, PROCESSED_DIR, OUTPUTS_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def load_yaml(name: str) -> dict[str, Any]:
    path = CONFIG_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a mapping: {path}")
    return data


def parse_month(value: str | None) -> str | None:
    if value is None:
        return None
    clean = value.strip()
    if len(clean) == 7 and clean[4] == "-":
        return clean
    raise ValueError(f"Expected month in YYYY-MM format, got {value!r}")

