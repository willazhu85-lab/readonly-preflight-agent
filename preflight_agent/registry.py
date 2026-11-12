"""Explicit tool allowlist and recursive result checks, not a code sandbox."""
import copy
import re
from typing import Callable

from preflight_agent.common import authority, canonical
from preflight_agent import tools


class ReadonlyViolation(ValueError):
    """A tool emitted an action-shaped field."""


def assert_readonly(value: object) -> None:
    forbidden = {"write", "action", "actions", "command", "commands", "execute", "exec", "delete",
                 "deploy", "publish", "approve", "mutation", "mutate", "shell", "restart"}
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ReadonlyViolation("result keys must be strings")
            if key == "authority":
                if child != authority() or any(v is not False for v in child.values()):
                    raise ReadonlyViolation("result claims authority")
                continue
            normalized = re.sub(r"([a-z])([A-Z])", r"\1_\2", key).lower()
            tokens = {token.removesuffix("s") for token in re.split(r"[^a-z0-9]+", normalized)}
            if forbidden.intersection(tokens):
                raise ReadonlyViolation("result contains prohibited capability field")
            assert_readonly(child)
    elif isinstance(value, list):
        for child in value:
            assert_readonly(child)
    elif value is not None and type(value) not in (str, int, float, bool):
        raise ReadonlyViolation("result must be JSON data")


class Registry:
    def __init__(self) -> None:
        self.tools: dict[str, Callable[[dict], dict]] = {
            "evidence": tools.evidence_index, "impact": tools.impact_analysis,
            "gate": tools.preflight_gate, "advisory": tools.advisory, "draft": tools.verdict_draft,
        }

    def call(self, name: str, context: dict) -> dict:
        if name not in self.tools:
            raise ValueError("unknown tool")
        # Each tool receives isolated data, preserving previous evidence and gate outputs.
        detached = copy.deepcopy({k: v for k, v in context.items() if k != "model"})
        if "model" in context:
            detached["model"] = context["model"]
        result = self.tools[name](detached)
        if not isinstance(result, dict):
            raise ReadonlyViolation("result must be a mapping")
        assert_readonly(result)
        canonical(result)
        return result
