"""Degrade-to-replay for the public "Ask the IPCA" box (spec_V3 §3.8).

The live Q&A (``answer_question``) needs a provider key. On the public demo the
key may be absent or the free-tier quota may run out — in which case the live
call degrades to ``mode="fallback"`` (a generic "AI unavailable" message). This
layer makes that degradation graceful: for a curated question we serve a
**pre-generated, audited** answer (``mode="replay"``) instead of the generic
message, so the demo always shows a grounded answer.

Design (kept lightweight, no new backend):
- ``answer_with_replay`` calls ``answer_question`` first. If the live answer is
  grounded (``mode="ai"``) or the question was **refused** (injection/off-scope),
  it is returned as-is — a replay must never mask a refusal or override a live
  answer. Only when the live path degraded do we look for a replay.
- Matching is **exact on the normalized question text** (curated questions are
  offered as buttons in the UI). No fuzzy/embedding match — a stranger's free
  text that we cannot ground simply gets the honest "unavailable" fallback.
- The replay file ``reports/qa/replay.json`` is generated once, BYOK, by the
  owner running ``python -m ipca_dashboard.ai.qa_replay`` with a key configured.
  It is committed; no key is ever written (answers only).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from ipca_dashboard.ai import SCHEMA_VERSION
from ipca_dashboard.ai.qa import QA_PROMPT_VERSION, QAResult, answer_question
from ipca_dashboard.config import PROJECT_ROOT

REPLAY_PATH = PROJECT_ROOT / "reports" / "qa" / "replay.json"

# The curated set the box advertises (the "face" of the product). These are the
# buttons shown in the UI and the questions the replay is generated for. All are
# in-scope (carry an inflation hint) and answerable from the processed data.
CURATED_QUESTIONS: list[str] = [
    "O que mais puxou a inflação do IPCA neste mês?",
    "A inflação está espalhada ou concentrada? Como está a difusão?",
    "Como estão os núcleos do IPCA em relação ao headline?",
    "Qual é o regime inflacionário atual e o que ele significa?",
    "Alimentação puxou ou segurou a inflação do mês?",
    "Como está a inflação acumulada em 12 meses?",
]


def _norm_q(question: str) -> str:
    """Normalize a question for exact replay matching (case/space-insensitive)."""
    return re.sub(r"\s+", " ", (question or "").strip().lower())


def load_replay(path: Path | None = None) -> dict[str, dict]:
    """Load the replay pairs as a {normalized_question: pair} map.

    Robust by design: a missing or malformed file yields an empty map so the
    Q&A box degrades to the honest fallback rather than crashing.
    """
    path = path or REPLAY_PATH
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, OSError):
        return {}
    pairs = raw.get("pairs", []) if isinstance(raw, dict) else raw
    out: dict[str, dict] = {}
    if isinstance(pairs, list):
        for pair in pairs:
            if isinstance(pair, dict) and isinstance(pair.get("question"), str):
                out[_norm_q(pair["question"])] = pair
    return out


def _replay_result(pair: dict, question: str, error: str | None) -> QAResult:
    """Build a QAResult that serves a pre-generated, audited answer."""
    provider = str(pair.get("provider", "replay"))
    return QAResult(
        answer=str(pair.get("answer", "")),
        claims=list(pair.get("claims", []) or []),
        evidence=list(pair.get("evidence", []) or []),
        trace={
            "prompt_version": QA_PROMPT_VERSION,
            "question": question,
            "replay": True,
            "generated_provider": provider,
        },
        metadata={
            "mode": "replay",
            "provider": provider,
            "schema_version": SCHEMA_VERSION,
            "replay": True,
        },
        mode="replay",
        provider_name=provider,
        refused=False,
        error=error,  # preserve why the live path degraded (auditable)
    )


def answer_with_replay(
    question: str,
    bcb: pd.DataFrame,
    ipca_items: pd.DataFrame,
    core_metrics: pd.DataFrame,
    alerts: pd.DataFrame,
    *,
    provider=None,
    core_set: str = "bcb_compact",
    replay_path: Path | None = None,
) -> QAResult:
    """Answer live; if the live path degraded, serve a curated replay if we have one.

    Never raises (delegates to ``answer_question``'s never-raise discipline).
    """
    result = answer_question(
        question, bcb, ipca_items, core_metrics, alerts,
        provider=provider, core_set=core_set,
    )
    # A grounded live answer wins; a refusal must NOT be masked by a replay.
    if result.mode in ("ai", "refused"):
        return result
    # Live path degraded (fallback/deterministic): use a replay if the question
    # is one we pre-generated; otherwise keep the honest "unavailable" fallback.
    pair = load_replay(replay_path).get(_norm_q(question))
    if pair is None:
        return result
    return _replay_result(pair, question, result.error)


# --- BYOK generation (owner runs once with a key configured) ----------------


def generate_replay(
    bcb: pd.DataFrame,
    ipca_items: pd.DataFrame,
    core_metrics: pd.DataFrame,
    alerts: pd.DataFrame,
    *,
    questions: list[str] | None = None,
    provider=None,
    reference_month: str | None = None,
    generated_at: str | None = None,
) -> dict:
    """Generate replay pairs for the curated questions. Keeps only grounded ones.

    Returns the artifact dict (also what gets written to reports/qa/replay.json).
    A question that does not come back grounded (mode != "ai") is skipped and
    reported, never shipped — the replay must be auditable.
    """
    questions = questions or CURATED_QUESTIONS
    pairs: list[dict] = []
    skipped: list[tuple[str, str]] = []
    for question in questions:
        result = answer_question(
            question, bcb, ipca_items, core_metrics, alerts, provider=provider
        )
        if result.mode != "ai":
            skipped.append((question, f"{result.mode}: {result.error or 'not grounded'}"))
            continue
        pairs.append(
            {
                "question": question,
                "answer": result.answer,
                "claims": result.claims,
                "evidence": result.evidence,
                "provider": result.provider_name,
                "mode": result.mode,
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "prompt_version": QA_PROMPT_VERSION,
        "reference_month": reference_month,
        "generated_at": generated_at,
        "pairs": pairs,
        "skipped": [{"question": q, "reason": r} for q, r in skipped],
    }


def main(argv: list[str] | None = None) -> None:  # pragma: no cover - BYOK entry point
    import argparse
    import logging
    from datetime import UTC, datetime

    from ipca_dashboard.ai.env import load_env_once
    from ipca_dashboard.config import PROCESSED_DIR

    parser = argparse.ArgumentParser(description="Generate the Ask-the-IPCA replay pairs (BYOK).")
    parser.add_argument("--out", default=str(REPLAY_PATH), help="Output replay.json path.")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level.upper()), format="%(levelname)s:%(message)s")
    logger = logging.getLogger(__name__)

    if load_env_once():
        logger.info("Loaded configuration from .env")

    def _load(name: str) -> pd.DataFrame:
        path = PROCESSED_DIR / name
        return pd.read_parquet(path) if path.exists() else pd.DataFrame()

    bcb = _load("bcb_series_monthly.parquet")
    if bcb.empty:
        raise SystemExit("No processed data found. Run the pipeline first.")
    items = _load("ipca_items_monthly.parquet")
    cores = _load("core_metrics_monthly.parquet")
    alerts = _load("alerts.parquet")

    reference_month = pd.to_datetime(bcb["date"]).max().strftime("%Y-%m")
    generated_at = datetime.now(UTC).isoformat(timespec="seconds")
    artifact = generate_replay(
        bcb, items, cores, alerts,
        reference_month=reference_month, generated_at=generated_at,
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Wrote %d replay pair(s) -> %s", len(artifact["pairs"]), out_path)
    for skip in artifact["skipped"]:
        logger.warning("Skipped (not grounded): %s — %s", skip["question"], skip["reason"])


if __name__ == "__main__":  # pragma: no cover
    main()
