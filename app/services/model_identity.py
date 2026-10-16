def matches_model(record: dict, model_id: str, source: str = "ms") -> bool:
    expected_source, expected_id = model_id.split("://", 1) if "://" in model_id else (source, model_id)
    actual = record.get("model_id")
    if not isinstance(actual, str):
        return False
    actual_source, actual_id = actual.split("://", 1) if "://" in actual else (record.get("source") or source, actual)
    declared_source = record.get("source")
    return actual_id == expected_id and actual_source == expected_source and (not declared_source or declared_source == actual_source)
