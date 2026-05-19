from __future__ import annotations

from stalcraft_market_analyzer.analysis.patch_impact import analyze_patch_notes


def test_analyze_patch_notes_stub_when_disabled(monkeypatch) -> None:
    monkeypatch.delenv("PATCH_IMPACT_LLM_ENABLED", raising=False)

    result = analyze_patch_notes(patch_version="1.2.3", patch_text="- buff foo\n- nerf bar\n")
    assert result["patch_version"] == "1.2.3"
    assert result["source"] == "stub"
    assert "impact" in result


def test_analyze_patch_notes_stub_when_enabled_but_no_key(monkeypatch) -> None:
    monkeypatch.setenv("PATCH_IMPACT_LLM_ENABLED", "true")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = analyze_patch_notes(patch_version="9.9.9", patch_text="x")
    assert result["source"] == "stub_missing_key"


def test_finalize_patch_result_derives_legacy_lists() -> None:
    from stalcraft_market_analyzer.analysis.patch_impact import PatchImpactStructured, finalize_patch_result

    structured = PatchImpactStructured.model_validate(
        {
            "severity": "high",
            "impact": "BUFF",
            "items": [
                {"item_name": "Spiral", "price_impact": "up"},
                {"item_name": "Cooler", "price_impact": "down"},
            ],
            "confidence": 0.8,
            "notes": "test",
        }
    )
    result = finalize_patch_result(patch_version="1.0.0", source="test", structured=structured)
    assert result["items"][0]["item_name"] == "Spiral"
    assert result["items"][0]["price_impact"] == "up"
    assert "Spiral" in result["buffed_items"]
    assert "Cooler" in result["nerfed_items"]
