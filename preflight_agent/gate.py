"""Pure decision policy. No language-model input participates here."""


def evaluate(evidence: dict, impact: dict) -> dict:
    reasons = []
    if evidence["missing"]:
        reasons.append("EVIDENCE_MISSING")
    if evidence["invalid"]:
        reasons.append("EVIDENCE_INVALID")
    if evidence["tests_failed"]:
        reasons.append("TESTS_FAILED")
    if reasons:
        decision = "BLOCK"
    elif impact["breaking_api"] and not evidence["migration_note"]:
        decision = "NEEDS_REVIEW"
        reasons.append("BREAKING_CHANGE_WITHOUT_MIGRATION")
    elif impact["dependency_changes"] or impact["config_changes"]:
        decision = "NEEDS_REVIEW"
        reasons.append("DEPENDENCY_OR_CONFIG_REVIEW")
    else:
        decision = "PASS"
        reasons.append("CHECKS_SATISFIED")
    return {"decision": decision, "reason_codes": reasons}
