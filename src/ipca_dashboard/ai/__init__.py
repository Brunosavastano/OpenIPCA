"""Optional, grounded AI layer for OpenIPCA.

The app works fully without this package. Nothing here calls a network by
default: the Tool API, evidence table and guardrails are deterministic and the
NoAIProvider needs no key. A hosted provider and brief generation arrive in CP7.

Contract (spec_V3 §3.2/§3.3): the model only ever sees the world through the
Tool API; every claim it makes must cite an evidence_id that exists in the
evidence table, or the guardrails reject it and the app falls back to the
deterministic brief.
"""

from __future__ import annotations

SCHEMA_VERSION = "brief_v1"
