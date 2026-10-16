from app.services.model_identity import matches_model


def test_modelscope_legacy_and_qualified_ids_match():
    for expected in ("owner/model", "ms://owner/model"):
        for actual in ("owner/model", "ms://owner/model"):
            assert matches_model({"model_id": actual}, expected)
            assert matches_model({"model_id": actual, "source": "ms"}, expected)


def test_other_sources_and_conflicting_source_do_not_match():
    assert not matches_model({"model_id": "hf://owner/model"}, "owner/model")
    assert not matches_model({"model_id": "owner/model", "source": "hf"}, "owner/model")
    assert not matches_model({"model_id": "ms://owner/model", "source": "hf"}, "owner/model")
    assert not matches_model({"model_id": "ms://owner/other"}, "owner/model")
