from __future__ import annotations


def classify_failure(stage: str | None, error_type: str | None, message: str | None) -> str:
    stage_text = (stage or "").lower()
    type_text = (error_type or "").lower()
    message_text = (message or "").lower()
    combined = " ".join([stage_text, type_text, message_text])

    if "archivevalidationerror" in type_text or "archive_validation" in stage_text:
        return "archive_validation_error"
    if "importerror" in type_text or "modulenotfounderror" in type_text or "no module named" in message_text:
        return "import_error"
    if "missing" in message_text and ("file" in message_text or "required member" in message_text):
        return "missing_file"
    if "deck" in combined and ("validation" in combined or "60-card" in combined or "deck.csv" in combined):
        return "deck_validation_error"
    if "timeout" in type_text or "timeout" in message_text or "max_steps" in message_text:
        return "timeout"
    if "invalid_action" in type_text or "invalid action" in combined or "option indexes" in message_text:
        return "invalid_action"
    if "illegal" in combined:
        return "illegal_state"
    if "battle_start_failed" in combined or "engine" in combined or "cg." in combined:
        return "engine_error"
    if "parse" in combined or "jsondecode" in combined or "csv" in combined:
        return "result_parse_error"
    if "exception" in type_text or "runtime" in combined:
        return "runtime_exception"
    return "unknown_error"
