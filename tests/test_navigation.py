from ipca_dashboard.navigation import parse_query_params, target_for_evidence


def test_query_params_accept_only_stable_public_values():
    parsed = parse_query_params(
        {
            "view": "decomposicao",
            "month": "2026-05",
            "evidence": "ev_item_mom_123",
            "item": "123",
        }
    )
    assert parsed.view == "decomposicao"
    assert parsed.month == "2026-05"
    assert parsed.item == "123"

    bad = parse_query_params(
        {"view": "admin", "month": "2026-99", "evidence": "<script>", "item": "1 OR 1"}
    )
    assert bad.view == bad.month == bad.evidence == bad.item == ""


def test_evidence_targets_cover_dashboard_domains_and_item_codes():
    assert target_for_evidence("ev_headline_mom", "2026-05").view == "executivo"
    assert target_for_evidence("ev_core_mean_mm3").view == "nucleos"
    assert target_for_evidence("ev_diffusion_mm3").view == "difusao"
    assert target_for_evidence("ev_alert_0").view == "alertas"
    assert target_for_evidence("ev_ref_base").view == "metodologia"
    item = target_for_evidence("ev_item_12m_1101001", "2026-05")
    assert item is not None and item.item == "1101001" and item.month == "2026-05"
    assert target_for_evidence("ev_unknown") is None
