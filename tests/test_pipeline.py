import pandas as pd
import pytest

from ipca_dashboard import pipeline


def _seed_processed(processed_dir, value):
    processed_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({"v": value})
    for name in pipeline.PROCESSED_FILENAMES.values():
        df.to_parquet(processed_dir / name, index=False)


def _stub_data_seams(monkeypatch, *, blocking: bool):
    """Replace the data-producing seams so build_command runs without network."""
    monkeypatch.setattr(pipeline, "ensure_project_dirs", lambda: None)
    monkeypatch.setattr(pipeline, "load_yaml", lambda name: {})
    monkeypatch.setattr(pipeline, "read_parquet", lambda path: pd.DataFrame())
    monkeypatch.setattr(pipeline, "transform_bcb_series", lambda raw: pd.DataFrame())
    monkeypatch.setattr(pipeline, "normalize_sidra_7060", lambda raw, cfg: pd.DataFrame())
    monkeypatch.setattr(pipeline, "transform_ipca_items", lambda items: pd.DataFrame())
    monkeypatch.setattr(pipeline, "build_core_metrics", lambda bcb, cfg: pd.DataFrame())
    monkeypatch.setattr(pipeline, "generate_alerts", lambda cfg, bcb, cores: pd.DataFrame())
    monkeypatch.setattr(pipeline, "build_diagnostic_text", lambda *a, **k: {"diagnostic": "ok"})
    status = "block" if blocking else "pass"
    report = pd.DataFrame([{"check": "forced", "status": status, "value": 0, "details": "t"}])
    monkeypatch.setattr(pipeline, "validate_all", lambda bcb, items, cfg: report)


def _redirect_paths(monkeypatch, tmp_path):
    processed = tmp_path / "processed"
    staging = tmp_path / "staging"
    monkeypatch.setattr(pipeline, "PROCESSED_DIR", processed)
    monkeypatch.setattr(pipeline, "PROCESSED_STAGING_DIR", staging)
    monkeypatch.setattr(pipeline, "VALIDATION_REPORT", tmp_path / "validation_report.csv")
    monkeypatch.setattr(pipeline, "DIAGNOSTIC_JSON", tmp_path / "diag.json")
    return processed, staging


def test_pipeline_does_not_overwrite_processed_on_blocking_validation(tmp_path, monkeypatch):
    processed, _ = _redirect_paths(monkeypatch, tmp_path)
    _seed_processed(processed, [1, 2, 3])  # good existing data
    _stub_data_seams(monkeypatch, blocking=True)

    with pytest.raises(pipeline.BlockingValidationError):
        pipeline.build_command(strict=True)

    # The good processed files must be untouched (not overwritten by the bad build).
    for name in pipeline.PROCESSED_FILENAMES.values():
        df = pd.read_parquet(processed / name)
        assert list(df["v"]) == [1, 2, 3]
    # Audit trail is still written even on abort.
    assert (tmp_path / "validation_report.csv").exists()


def test_pipeline_promotes_when_validation_passes(tmp_path, monkeypatch):
    processed, _ = _redirect_paths(monkeypatch, tmp_path)
    _seed_processed(processed, [1, 2, 3])
    _stub_data_seams(monkeypatch, blocking=False)

    pipeline.build_command(strict=True)

    # Promotion replaced the seed with the freshly built (empty) frames.
    for name in pipeline.PROCESSED_FILENAMES.values():
        df = pd.read_parquet(processed / name)
        assert "v" not in df.columns


def test_promote_staging_to_processed_is_per_file(tmp_path, monkeypatch):
    processed = tmp_path / "processed"
    staging = tmp_path / "staging"
    processed.mkdir()
    staging.mkdir()
    monkeypatch.setattr(pipeline, "PROCESSED_DIR", processed)
    monkeypatch.setattr(pipeline, "PROCESSED_STAGING_DIR", staging)

    _seed_processed(processed, [0])  # old content
    for name in pipeline.PROCESSED_FILENAMES.values():
        pd.DataFrame({"v": [9]}).to_parquet(staging / name, index=False)

    pipeline._promote_staging_to_processed(pipeline.PROCESSED_FILENAMES)

    for name in pipeline.PROCESSED_FILENAMES.values():
        assert list(pd.read_parquet(processed / name)["v"]) == [9]  # promoted
        assert not (staging / name).exists()  # moved, not copied
