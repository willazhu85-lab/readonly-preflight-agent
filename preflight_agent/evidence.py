"""Bounded read-only snapshot and strict synthetic evidence validation."""
import json
from pathlib import Path
from typing import Any

REQUIRED = ("changed_files.json", "test_report.json", "dependency_diff.json", "config_diff.json", "changelog.md")
MAX_FILE_BYTES = 16_384
MAX_TOTAL_BYTES = 40_000


def snapshot(root: Path) -> dict[str, str]:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("candidate must be a directory, not a symlink")
    files: dict[str, str] = {}
    total = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("candidate symlink forbidden")
        if path.is_dir():
            continue
        if not path.is_file() or len(files) >= 32:
            raise ValueError("candidate file count or type invalid")
        raw = path.open("rb")
        with raw:
            content = raw.read(MAX_FILE_BYTES + 1)
        total += len(content)
        if len(content) > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES:
            raise ValueError("candidate evidence too large")
        files[path.relative_to(root).as_posix()] = content.decode("utf-8")
    return files


def string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(x, str) and x.strip() for x in value)


def valid_path(value: str) -> bool:
    return not value.startswith("/") and "\\" not in value and all(p not in ("", ".", "..") for p in value.split("/"))


def parse(files: dict[str, str]) -> tuple[dict, list[str]]:
    """Invalid or absent evidence never becomes a successful check."""
    data: dict = {}
    invalid: list[str] = []
    for name in REQUIRED:
        if name not in files:
            continue
        try:
            value = files[name] if name.endswith(".md") else json.loads(files[name])
            if name == "changed_files.json":
                ok = string_list(value) and bool(value) and all(valid_path(x) for x in value)
            elif name == "test_report.json":
                ok = isinstance(value, dict) and set(value) == {"passed", "failed", "total"}
                ok = ok and all(type(value[k]) is int and value[k] >= 0 for k in value)
                ok = ok and value["total"] > 0 and value["total"] == value["passed"] + value["failed"]
            elif name == "dependency_diff.json":
                ok = isinstance(value, dict) and set(value) == {"added", "removed", "updated"}
                ok = ok and all(string_list(v) for v in value.values())
            elif name == "config_diff.json":
                ok = isinstance(value, dict) and set(value) == {"changed_keys", "breaking_api"}
                ok = ok and string_list(value["changed_keys"]) and type(value["breaking_api"]) is bool
            else:
                ok = bool(value.strip())
            if not ok:
                raise ValueError("invalid schema")
            data[name] = value
        except (ValueError, TypeError, KeyError):
            invalid.append(name)
    return data, sorted(invalid)
