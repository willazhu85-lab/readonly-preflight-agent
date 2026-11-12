"""Small declarative workflow interpreter with explicit policy invariants."""
from pathlib import Path
from typing import Any

import yaml

from preflight_agent.common import authority, digest, text_digest
from preflight_agent.evidence import snapshot
from preflight_agent.llm import model_from_env
from preflight_agent.registry import ReadonlyViolation, Registry
from preflight_agent.store import TraceStore

DEFAULT_WORKFLOW = Path(__file__).resolve().parents[1] / "workflows" / "release_preflight.yaml"


def workflow(text: str, registry: Registry) -> list[dict]:
    try:
        spec = yaml.safe_load(text)
        if set(spec) != {"version", "steps"} or type(spec["version"]) is not int or spec["version"] != 1:
            raise ValueError("workflow schema")
        steps = spec["steps"]
        order = ["evidence", "impact", "gate", "advisory", "draft"]
        if not isinstance(steps, list) or [s["tool"] for s in steps] != order:
            raise ValueError("workflow requires ordered evidence, impact, gate, advisory, draft")
        for step in steps:
            if set(step) != {"tool", "required", "run_when"} or type(step["required"]) is not bool:
                raise ValueError("step schema")
            if step["tool"] not in registry.tools:
                raise ValueError("unknown tool")
            if step["run_when"] not in ("always", "never", "gate_pass", "gate_not_pass"):
                raise ValueError("unknown condition")
            if step["tool"] != "advisory" and (not step["required"] or step["run_when"] != "always"):
                raise ValueError("deterministic steps must be required and unconditional")
        return steps
    except (TypeError, KeyError, AttributeError, yaml.YAMLError) as exc:
        raise ValueError("invalid workflow") from exc


def run(workflow_id: str, candidate: Path, trace_root: Path, *, workflow_path: Path = DEFAULT_WORKFLOW,
        model: Any = None, registry: Registry | None = None) -> dict:
    if trace_root.resolve().is_relative_to(candidate.resolve()):
        raise ValueError("trace storage must be outside candidate")
    registry = registry if registry is not None else Registry()
    model = model if model is not None else model_from_env()
    spec_text = workflow_path.read_text(encoding="utf-8")
    steps = workflow(spec_text, registry)
    files = snapshot(candidate)
    fingerprint = digest({"engine": 1, "files": files, "workflow": text_digest(spec_text), "model": model.identity()})
    store = TraceStore(trace_root)
    cached = store.load(workflow_id, fingerprint)
    if cached is not None:
        return cached
    trace = {"schema": "preflight-trace-v1", "workflow_id": workflow_id, "inputs_digest": fingerprint,
             "workflow_digest": text_digest(spec_text), "status": "COMPLETED", "steps": []}
    context = {"files": files, "model": model}
    for step in steps:
        name, condition = step["tool"], step["run_when"]
        gate_pass = context.get("gate", {}).get("decision") == "PASS"
        enabled = {"always": True, "never": False, "gate_pass": gate_pass, "gate_not_pass": not gate_pass}[condition]
        visible = {k: v for k, v in context.items() if k != "model"}
        row = {"tool": name, "inputs_digest": digest(visible), "status": "SKIPPED", "output": None,
               "reason_codes": ["CONDITION_FALSE"]}
        trace["steps"].append(row)
        try:
            if not enabled:
                if step["required"]:
                    raise ValueError("required step condition false")
                continue
            output = registry.call(name, context)
            row.update(status="COMPLETED", output=output, reason_codes=output.get("reason_codes", []))
            context[name] = output
        except Exception as exc:
            readonly = isinstance(exc, ReadonlyViolation)
            reason = ("READONLY_VIOLATION" if readonly else
                      ("ADVISORY_UNAVAILABLE" if name == "advisory" else "TOOL_FAILED"))
            row.update(status="FAILED", output=None, reason_codes=[reason])
            if step["required"] or readonly:
                trace["status"] = "FAILED"
                trace["final_draft"] = {"decision": "BLOCK", "reason_codes": [reason],
                                        "advisory_only": True, "human_approval_required": True,
                                        "authority": authority(), "advisory": None}
                break
    else:
        trace["final_draft"] = context["draft"]
    return store.save(trace)
