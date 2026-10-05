from novel_ai.integrations import INTEGRATIONS, integration_summary, list_integrations, probe_integrations


def test_registry_has_large_cross_category_set():
    assert len(INTEGRATIONS) >= 30
    categories = {item.category for item in INTEGRATIONS}
    assert {"story_generation", "chinese_nlp", "memory_retrieval", "evaluation", "model_runtime"} <= categories


def test_no_license_projects_are_reference_only():
    risky = [item for item in INTEGRATIONS if item.license == "NO_LICENSE_DETECTED"]
    assert risky
    assert all(item.mode == "architecture-reference-only" for item in risky)


def test_probe_is_non_destructive():
    rows = probe_integrations()
    assert len(rows) == len(INTEGRATIONS)
    assert all("installed" in row for row in rows)


def test_filter_and_summary():
    assert list_integrations(category="evaluation")
    summary = integration_summary()
    assert sum(summary.values()) == len(INTEGRATIONS)
