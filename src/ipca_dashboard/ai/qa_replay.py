"""Degrade-to-replay for the public "Ask the IPCA" box (spec_V3 §3.8).

The live Q&A (``answer_question``) needs a provider key. On the published app the
key may be absent or the free-tier quota may run out; the current-data
deterministic floor still answers common intents. For a curated question this
layer can serve a richer **pre-generated, audited** answer (``mode="replay"``).

Design (kept lightweight, no new backend):
- ``answer_with_replay`` calls ``answer_question`` first. If the live answer is
  grounded (``mode="ai"``) or the question was **refused** (injection/off-scope),
  it is returned as-is — a replay must never mask a refusal or override a live
  answer. Only when the live path degraded do we look for a replay.
- Matching is **exact on the normalized question text** (curated questions are
  offered as buttons in the UI). No fuzzy/embedding match — a stranger's free
  text that the deterministic floor cannot ground gets an explicit no-evidence response.
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
from ipca_dashboard.ai.staleness import is_stale
from ipca_dashboard.config import PROJECT_ROOT

REPLAY_PATH = PROJECT_ROOT / "reports" / "qa" / "replay.json"
MAX_REPLAY_BYTES = 2_000_000

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
    Q&A box keeps its deterministic floor rather than crashing.
    """
    path = path or REPLAY_PATH
    try:
        if path.stat().st_size > MAX_REPLAY_BYTES:
            return {}
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, OSError, RecursionError):
        return {}
    pairs = raw.get("pairs", []) if isinstance(raw, dict) else raw
    out: dict[str, dict] = {}
    if isinstance(pairs, list):
        for pair in pairs:
            if isinstance(pair, dict) and isinstance(pair.get("question"), str):
                out[_norm_q(pair["question"])] = pair
    return out


def _replay_reference_month(path: Path | None = None) -> str | None:
    """The replay artifact's reference month (top-level field), robust to bad files."""
    path = path or REPLAY_PATH
    try:
        if path.stat().st_size > MAX_REPLAY_BYTES:
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, OSError, RecursionError):
        return None
    if isinstance(raw, dict):
        month = raw.get("reference_month")
        return str(month) if month else None
    return None


def _data_reference_month(bcb: pd.DataFrame) -> str:
    """Latest data month, or empty string when the month cannot be known."""
    try:
        dates = bcb["date"]
        latest = pd.to_datetime(dates, errors="coerce").max()
    except Exception:  # noqa: BLE001 - unknown month must not crash Q&A fallback
        return ""
    return latest.strftime("%Y-%m") if pd.notna(latest) else ""


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
    # Live path degraded (fallback/deterministic): a fresh audited replay remains
    # the richer answer for curated prompts; otherwise keep the current-data
    # deterministic result (or the explicit no-evidence response).
    # Safety net: never serve a replay whose reference month lags the data (a rare
    # partial-refresh state) — fall back to the honest "unavailable" result.
    if is_stale(_replay_reference_month(replay_path), _data_reference_month(bcb)):
        return result
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
        if not _is_grounded_replay_result(result):
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


def _is_grounded_replay_result(result: QAResult) -> bool:
    if result.mode != "ai" or not result.claims:
        return False
    evidence_ids = {ev.get("evidence_id") for ev in result.evidence}
    for claim in result.claims:
        ids = claim.get("evidence_ids", []) or []
        if ids and all(evidence_id in evidence_ids for evidence_id in ids):
            return True
    return False


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

    grounded = len(artifact["pairs"])
    skipped = len(artifact["skipped"])
    total = grounded + skipped
    for skip in artifact["skipped"]:
        logger.warning("Skipped (not grounded): %s — %s", skip["question"], skip["reason"])
    logger.info("Wrote %d/%d grounded replay pair(s) -> %s", grounded, total, out_path)
    if grounded == 0:
        logger.error(
            "NO replay pairs were grounded. The deterministic Q&A remains available, but "
            "curated prompts will not have the richer audited replay. Configure a provider "
            "key (a stronger model such as openai/anthropic is recommended for the one-off "
            "replay) and re-run."
        )
    elif skipped:
        logger.warning(
            "%d/%d question(s) did not ground. Consider a stronger provider/model for the "
            "replay, or revise those questions, then re-run.", skipped, total,
        )


if __name__ == "__main__":  # pragma: no cover
    main()
