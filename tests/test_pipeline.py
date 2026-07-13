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
    monkeypatch.setattr(
        pipeline,
        "validate_all",
        lambda bcb, items, cfg, expected_month=None: report,
    )


def _redirect_paths(monkeypatch, tmp_path):
    processed = tmp_path / "processed"
    staging = tmp_path / "staging"
    monkeypatch.setattr(pipeline, "PROCESSED_DIR", processed)
    monkeypatch.setattr(pipeline, "PROCESSED_STAGING_DIR", staging)
    monkeypatch.setattr(pipeline, "VALIDATION_REPORT", tmp_path / "validation_report.csv")
    monkeypatch.setattr(pipeline, "DIAGNOSTIC_JSON", tmp_path / "diag.json")
    monkeypatch.setattr(pipeline, "RELEASE_STATE_JSON", tmp_path / "release_state.json")
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


def test_strict_freshness_warn_does_not_overwrite_processed(tmp_path, monkeypatch):
    processed, _ = _redirect_paths(monkeypatch, tmp_path)
    _seed_processed(processed, [1, 2, 3])
    _stub_data_seams(monkeypatch, blocking=False)
    report = pd.DataFrame(
        [
            {
                "check": "critical_series_freshness",
                "status": "warn",
                "value": "Servicos",
                "details": "Serie critica defasada.",
            }
        ]
    )
    monkeypatch.setattr(
        pipeline,
        "validate_all",
        lambda bcb, items, cfg, expected_month=None: report,
    )

    with pytest.raises(pipeline.BlockingValidationError):
        pipeline.build_command(strict=True)

    for name in pipeline.PROCESSED_FILENAMES.values():
        df = pd.read_parquet(processed / name)
        assert list(df["v"]) == [1, 2, 3]


def test_pipeline_promotes_when_validation_passes(tmp_path, monkeypatch):
    processed, _ = _redirect_paths(monkeypatch, tmp_path)
    _seed_processed(processed, [1, 2, 3])
    _stub_data_seams(monkeypatch, blocking=False)

    pipeline.build_command(strict=True)

    # Promotion replaced the seed with the freshly built (empty) frames.
    for name in pipeline.PROCESSED_FILENAMES.values():
        df = pd.read_parquet(processed / name)
        assert "v" not in df.columns


def test_parser_defaults_pin_sgs_2012_and_sidra_2020():
    """The monthly workflow runs `pipeline run --strict` with NO flags — these
    defaults are the single source of truth for the public data window. SGS from
    2012 is what makes percentile_since_2012 honest; regressing it would bias
    every percentile and the public regime badge."""
    parser = pipeline.build_parser()
    for command in ("run", "fetch"):
        args = parser.parse_args([command])
        assert args.start_sgs == "2012-01" == pipeline.DEFAULT_SGS_START
        assert args.start_sidra == "2020-01" == pipeline.DEFAULT_SIDRA_START


def test_strict_checks_include_history_depth_tripwire():
    assert "sgs_history_depth" in pipeline.STRICT_REQUIRED_PASS_CHECKS
    assert "stl_coverage" not in pipeline.STRICT_REQUIRED_PASS_CHECKS


def test_fetch_command_passes_separate_starts(monkeypatch, tmp_path):
    received = {}
    monkeypatch.setattr(pipeline, "ensure_project_dirs", lambda: None)
    monkeypatch.setattr(pipeline, "load_yaml", lambda name: {})
    monkeypatch.setattr(
        pipeline,
        "fetch_all_sgs",
        lambda cfg, start, end: received.update(sgs=start) or pd.DataFrame(),
    )
    monkeypatch.setattr(
        pipeline,
        "fetch_sidra_7060",
        lambda cfg, start, end: received.update(sidra=start) or pd.DataFrame(),
    )
    monkeypatch.setattr(pipeline, "write_parquet", lambda df, path: None)

    pipeline.fetch_command(start_sgs="2012-01", start_sidra="2020-01", end=None)
    assert received == {"sgs": "2012-01", "sidra": "2020-01"}


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


def test_replace_by_key_is_idempotent_and_prefers_fresh_rows():
    existing = pd.DataFrame(
        {
            "series_short_name": ["IPCA", "IPCA"],
            "date": pd.to_datetime(["2024-01-01", "2024-02-01"]),
            "value": [0.4, 0.5],
        }
    )
    fresh = pd.DataFrame(
        {
            "series_short_name": ["IPCA", "IPCA"],
            "date": pd.to_datetime(["2024-02-01", "2024-03-01"]),
            "value": [0.55, 0.6],
        }
    )
    once = pipeline._replace_by_key(existing, fresh, ["series_short_name", "date"])
    twice = pipeline._replace_by_key(once, fresh, ["series_short_name", "date"])
    assert len(once) == len(twice) == 3
    assert once.loc[once["date"] == pd.Timestamp("2024-02-01"), "value"].item() == 0.55
    pd.testing.assert_frame_equal(once, twice)


def test_sidra_target_payload_requires_every_configured_variable():
    config = {
        "variables": {
            name: {"code": code} for name, code in {"mom": 63, "weight": 66}.items()
        }
    }
    complete = pd.DataFrame(
        [
            {"D2C": str(variable), "D3C": "202406", "D4C": code, "V": "1.0"}
            for variable in (63, 66)
            for code in ("1", "2")
        ]
    )
    pipeline._validate_sidra_target_payload(complete, config, "2024-06")
    with pytest.raises(pipeline.IncompleteSourceDataError):
        pipeline._validate_sidra_target_payload(
            complete[complete["D2C"] == "63"], config, "2024-06"
        )
    incomplete_value = complete.copy()
    incomplete_value.loc[0, "V"] = "..."
    with pytest.raises(pipeline.IncompleteSourceDataError):
        pipeline._validate_sidra_target_payload(incomplete_value, config, "2024-06")


def test_incremental_merge_recomputes_to_same_result_as_full_build():
    dates = pd.date_range("2023-01-01", periods=13, freq="MS")
    raw_bcb = pd.DataFrame(
        [
            {
                "date": date,
                "value": 0.1 + index / 100,
                "series_group": "headline",
                "series_short_name": "IPCA",
                "series_name": "IPCA",
                "sgs_code": 433,
                "unit": "pct_mom",
                "source": "BCB/SGS",
                "fetched_at": "x",
            }
            for index, date in enumerate(dates)
        ]
    )
    full_bcb = pipeline.transform_bcb_series(raw_bcb)
    base_bcb = pipeline.transform_bcb_series(raw_bcb.iloc[:-1])
    merged_raw = pipeline._replace_by_key(
        pipeline._processed_bcb_as_raw(base_bcb), raw_bcb.iloc[-2:], ["series_short_name", "date"]
    )
    incremental_bcb = pipeline.transform_bcb_series(merged_raw)
    pd.testing.assert_frame_equal(
        incremental_bcb.reset_index(drop=True), full_bcb.reset_index(drop=True), check_dtype=False
    )

    normalized = pd.DataFrame(
        [
            {
                "date": date,
                "source": "IBGE/SIDRA",
                "item_code": "1",
                "classification_code": "1",
                "item_name": "Grupo",
                "level": "group",
                "parent_classification_code": "",
                "group_classification_code": "1",
                "mom": 0.2,
                "weight": 100.0,
                "ytd": 1.0,
                "yoy": 4.0,
            }
            for date in dates
        ]
    )
    full_items = pipeline.transform_ipca_items(normalized)
    base_items = pipeline.transform_ipca_items(normalized.iloc[:-1])
    merged_items = pipeline._replace_by_key(
        pipeline._processed_items_as_normalized(base_items),
        normalized.iloc[-1:],
        ["date", "classification_code"],
    )
    incremental_items = pipeline.transform_ipca_items(merged_items)
    pd.testing.assert_frame_equal(
        incremental_items.reset_index(drop=True),
        full_items.reset_index(drop=True),
        check_dtype=False,
    )


def _seed_refresh_base(tmp_path, monkeypatch, latest="2026-05-01"):
    processed = tmp_path / "processed"
    processed.mkdir()
    paths = {
        "bcb": processed / "bcb.parquet",
        "items": processed / "items.parquet",
        "cores": processed / "cores.parquet",
        "alerts": processed / "alerts.parquet",
    }
    pd.DataFrame(
        [
            {
                "date": pd.Timestamp(latest),
                "series_short_name": "IPCA",
                "series_group": "headline",
                "series_name": "IPCA",
                "sgs_code": 433,
                "unit": "pct_mom",
                "source": "BCB/SGS",
                "mom": 0.4,
            }
        ]
    ).to_parquet(paths["bcb"], index=False)
    pd.DataFrame(
        [
            {
                "date": pd.Timestamp(latest),
                "classification_code": "1",
                "item_code": "1",
                "item_name": "Grupo",
                "level": "group",
                "source": "IBGE/SIDRA",
                "mom": 0.2,
                "weight": 100.0,
                "ytd": 1.0,
                "yoy": 4.0,
                "parent_classification_code": "",
                "group_classification_code": "1",
            }
        ]
    ).to_parquet(paths["items"], index=False)
    pd.DataFrame().to_parquet(paths["cores"], index=False)
    pd.DataFrame().to_parquet(paths["alerts"], index=False)
    monkeypatch.setattr(pipeline, "PROCESSED_BCB", paths["bcb"])
    monkeypatch.setattr(pipeline, "PROCESSED_ITEMS", paths["items"])
    monkeypatch.setattr(pipeline, "PROCESSED_CORES", paths["cores"])
    monkeypatch.setattr(pipeline, "PROCESSED_ALERTS", paths["alerts"])
    monkeypatch.setattr(pipeline, "ensure_project_dirs", lambda: None)
    return paths


def test_refresh_latest_uses_incremental_fetch_and_expected_month(tmp_path, monkeypatch):
    _seed_refresh_base(tmp_path, monkeypatch)
    received = {}
    sidra_config = {
        "variables": {
            name: {"code": code}
            for name, code in {"mom": 63, "weight": 66, "ytd": 69, "yoy": 2265}.items()
        }
    }
    monkeypatch.setattr(
        pipeline,
        "load_yaml",
        lambda name: sidra_config if name == "sidra_7060.yaml" else {},
    )

    def fake_bcb(config, start, end):
        received["bcb_window"] = (start, end)
        return pd.DataFrame(
            [
                {
                    "date": pd.Timestamp("2026-06-01"),
                    "value": 0.5,
                    "series_short_name": "IPCA",
                    "series_group": "headline",
                    "series_name": "IPCA",
                    "sgs_code": 433,
                    "unit": "pct_mom",
                    "source": "BCB/SGS",
                    "fetched_at": "now",
                }
            ]
        )

    raw_sidra = pd.DataFrame(
        [
            {"D2C": str(variable), "D3C": "202606", "D4C": "1", "V": "1.0"}
            for variable in (63, 66, 69, 2265)
        ]
    )
    fresh_items = pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2026-06-01"),
                "classification_code": "1",
                "item_code": "1",
                "item_name": "Grupo",
                "level": "group",
                "source": "IBGE/SIDRA",
                "mom": 0.3,
                "weight": 100.0,
                "ytd": 2.0,
                "yoy": 4.1,
                "parent_classification_code": "",
                "group_classification_code": "1",
            }
        ]
    )
    monkeypatch.setattr(pipeline, "fetch_all_sgs", fake_bcb)
    monkeypatch.setattr(pipeline, "fetch_sidra_7060", lambda *args, **kwargs: raw_sidra)
    monkeypatch.setattr(pipeline, "normalize_sidra_7060", lambda raw, cfg: fresh_items)
    monkeypatch.setattr(pipeline, "next_release_date", lambda month: "2026-08-11")

    def capture_build(raw_bcb, items, **kwargs):
        received["build"] = (raw_bcb, items, kwargs)

    monkeypatch.setattr(pipeline, "_build_from_inputs", capture_build)
    mode = pipeline.refresh_latest_command(
        "2026-06",
        strict=True,
        detected_at="2026-07-10T12:03:00+00:00",
        source_modified_at="2026-07-10",
    )
    assert mode == "incremental"
    assert received["bcb_window"] == ("2024-07", "2026-06")
    raw_bcb, items, kwargs = received["build"]
    assert set(pd.to_datetime(raw_bcb["date"]).dt.strftime("%Y-%m")) == {"2026-05", "2026-06"}
    assert set(pd.to_datetime(items["date"]).dt.strftime("%Y-%m")) == {"2026-05", "2026-06"}
    assert kwargs["strict"] is True and kwargs["expected_month"] == "2026-06"
    assert kwargs["release_context"]["next_release_date"] == "2026-08-11"


def test_refresh_latest_is_noop_when_month_is_already_published(tmp_path, monkeypatch):
    _seed_refresh_base(tmp_path, monkeypatch, latest="2026-06-01")
    monkeypatch.setattr(
        pipeline,
        "fetch_all_sgs",
        lambda *args, **kwargs: pytest.fail("network must not run for a current month"),
    )
    assert pipeline.refresh_latest_command("2026-06", strict=True) == "current"


def test_refresh_latest_falls_back_to_full_when_gap_exceeds_one_month(tmp_path, monkeypatch):
    _seed_refresh_base(tmp_path, monkeypatch, latest="2026-04-01")
    monkeypatch.setattr(pipeline, "next_release_date", lambda month: "")
    received = {}
    monkeypatch.setattr(
        pipeline,
        "run_command",
        lambda **kwargs: received.update(kwargs),
    )
    assert pipeline.refresh_latest_command("2026-06", strict=True) == "full"
    assert received["start_sgs"] == pipeline.DEFAULT_SGS_START
    assert received["start_sidra"] == pipeline.DEFAULT_SIDRA_START
    assert received["expected_month"] == "2026-06"
