"""Tools consume detached in-memory evidence; they receive no filesystem handles."""
from preflight_agent.common import authority, text_digest
from preflight_agent.evidence import REQUIRED, parse
from preflight_agent.gate import evaluate


def evidence_index(context: dict) -> dict:
    files = context["files"]
    data, invalid = parse(files)
    report = data.get("test_report.json", {})
    missing = sorted(set(REQUIRED) - files.keys())
    return {
        "available": sorted(files), "missing": missing, "invalid": invalid,
        "digests": {name: text_digest(text) for name, text in sorted(files.items())},
        "tests_failed": report.get("failed", 0) > 0,
        "migration_note": bool(files.get("migration.md", "").strip()),
        "reason_codes": (["EVIDENCE_MISSING"] if missing else []) + (["EVIDENCE_INVALID"] if invalid else []),
    }


def impact_analysis(context: dict) -> dict:
    data, _ = parse(context["files"])
    changed = data.get("changed_files.json", [])
    config = data.get("config_diff.json", {})
    dependencies = data.get("dependency_diff.json", {})
    contracts = [p for p in changed if p.startswith(("api/", "schemas/"))]
    # An API/schema touch is conservatively treated as potentially breaking.
    return {
        "modules": sorted({p.split("/")[0] for p in changed}),
        "contracts": contracts,
        "breaking_api": bool(contracts) or config.get("breaking_api", False),
        "dependency_changes": any(dependencies.values()),
        "config_changes": bool(config.get("changed_keys", [])),
        "reason_codes": ["API_CONTRACT_TOUCHED"] if contracts else [],
    }


def preflight_gate(context: dict) -> dict:
    return evaluate(context["evidence"], context["impact"])


def advisory(context: dict) -> dict:
    from preflight_agent.llm import advise
    inputs = {key: context[key] for key in ("files", "evidence", "impact", "gate")}
    return advise(inputs, context["model"])


def verdict_draft(context: dict) -> dict:
    return {
        **context["gate"], "human_approval_required": True,
        "advisory": context.get("advisory"), "advisory_only": True, "authority": authority(),
    }
