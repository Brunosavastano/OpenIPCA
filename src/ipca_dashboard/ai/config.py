"""AI layer configuration: model is config, not code (spec_V3 §3.4).

Reads environment variables only (BYOK). AI is OFF by default; with no key the
app uses NoAIProvider. No key is ever logged or serialised.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AIConfig:
    enabled: bool
    provider: str  # "none" or any provider name registered in the registry

    @property
    def is_active(self) -> bool:
        return self.enabled and self.provider != "none"


def load_ai_config() -> AIConfig:
    enabled = os.environ.get("OPENIPCA_AI_ENABLED", "false").strip().lower() in {"1", "true", "yes"}
    provider = os.environ.get("OPENIPCA_AI_PROVIDER", "none").strip().lower() or "none"
    return AIConfig(enabled=enabled, provider=provider)
