# Read-only Preflight Agent

A small Python portfolio sample that reviews **synthetic release evidence**, runs
explicit checks, and prepares a verdict draft for a human approver. It combines a
deterministic workflow with a tightly scoped AI explanation step.

**Sample project:** fictional projects and supplied reports, not a production
approval system. It does not run tests on a candidate, inspect a real repository,
change a release, or approve anything. No model or network access is needed for
the demo. Intended public repository: `willazhu85-lab/readonly-preflight-agent`.

## Architecture

```text
Candidate folder (read only)       YAML workflow (trusted policy)
              |                              |
      bounded UTF-8 snapshot                 |
              +----------> Workflow runner <-+
                               |
                     Allowlisted tool registry
                               |
                 1. Evidence index + digests
                 2. Change / contract impact
                 3. Deterministic preflight gate
                               |
                 4. Validated advisory boundary
                    +-- ScriptedModel (default, offline)
                    +-- Optional HTTP model
                               |
                 5. Human verdict draft
                    decision copied from gate
                               |
                 Digest-bound JSON trace store
                    (separate output directory)
```

The runner owns persistence; tools receive detached in-memory data. Every tool
result passes a recursive check for action-shaped fields. A violation aborts the
run and records a BLOCK draft without retaining the prohibited payload. Every
successful advisory and draft declares `advisory_only: true` and all authority
flags are `false`.

## Run the offline demo

Use Python 3.11+ with PyYAML and pytest already available. Dependencies are listed
in `requirements.txt`; the application itself uses the standard library and
PyYAML. From the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 python -B demo/run_demo.py
```

This always selects `ScriptedModel`, even if HTTP environment variables are set.
It runs all three candidates, prints each step and explanation, verifies an
identical replay, and removes its temporary trace directory on exit.

| Candidate | Fictional project | Expected draft | Why |
| --- | --- | --- | --- |
| `examples/clean` | Cedar Notes | PASS | Complete evidence; all reported tests pass |
| `examples/blocked` | Maple Canvas | BLOCK | Two failing tests and missing dependency evidence |
| `examples/review` | Lumen Catalog | NEEDS_REVIEW | API contract touched; no migration note |

PASS means only that this sample's checks were satisfied. Every verdict still
requires a human approver.

## Tests

```bash
PYTHONDONTWRITEBYTECODE=1 python -B -m pytest -q -p no:cacheprovider
```

Tests cover YAML conditions, required steps, the tool allowlist, recursive
read-only assertions, replay and input mismatch, trace corruption, all three
decisions, invalid evidence, prompt injection, response limits, stable receipt
hashes, and the HTTP adapter with an injected opener. Tests make no network calls.
`pytest.ini` disables the cache provider; `-B` prevents bytecode artifacts.

## Evidence contract and gate rules

A candidate contains:

- `changed_files.json`: nonempty array of relative changed paths.
- `test_report.json`: integer `passed`, `failed`, `total`; counts must agree and
  total must be positive. Boolean counts are rejected.
- `dependency_diff.json`: string arrays `added`, `removed`, `updated`.
- `config_diff.json`: string array `changed_keys` and boolean `breaking_api`.
- `changelog.md`: nonempty release notes.
- Optional `migration.md`: nonempty migration instructions.

All candidate files, including extra evidence, participate in the input identity.
Limits: 32 files, 16 KiB per file, 40,000 bytes total. Symlinks are rejected.
Changed paths are data; they are never opened or executed.

The gate gives BLOCK priority to missing evidence, invalid schemas, or failing
tests. Otherwise, an API/schema touch (conservatively treated as potentially
breaking), or an explicit breaking API flag, needs a migration note. Without
one it returns NEEDS_REVIEW. Dependency or configuration changes independently
require review. Other complete, passing evidence returns PASS. Gate reason codes
are stable strings; evidence and impact steps have their own diagnostic codes.
A migration note's **presence** is checked; its correctness requires human review.

The YAML has a deliberately small vocabulary: five ordered tools, `required`,
and `run_when` values `always`, `never`, `gate_pass`, `gate_not_pass`. The four
deterministic steps must be required and unconditional. Only the advisory may
be conditional or optional; the default runs it for all decisions. Unknown
conditions/tools, invalid step schemas, and reordering are rejected before any
model call. No expression evaluation or dynamic imports are supported.

## What the LLM can and cannot do

The guard recomputes the evidence index, impact analysis, and gate before calling
any model. Mismatched bindings, invalid evidence schemas, or oversized input
refuse the call. Missing evidence is valid input for a BLOCK explanation.

The prompt separates fixed system instructions from one JSON user message whose
contents are labeled `untrusted_evidence`. Evidence text, including apparent
instructions or role labels, stays inside JSON data. The response must finish
with `stop` and contain exactly two nonempty JSON string fields: `explanation`
and `suggested_next_step`, with a 1,200-byte response and 100-word total limit.
Empty, truncated, malformed, extra-field, and oversized responses fail closed.

The model can summarize observed reasons and suggest a step for human review.
It cannot change reason codes, choose the final verdict, call tools, write files,
or authorize actions. The prompt is guidance, **not a guarantee** that model prose
is correct. A malicious model may still produce misleading explanation text;
the deterministic verdict remains independent. Treat all advisory text as
untrusted, even when it passed structural validation.

An optional advisory failure records `ADVISORY_UNAVAILABLE`, produces no usable
advisory or receipt, and leaves the gate decision intact. A required step failure
blocks the workflow. A read-only violation always blocks it, including in an
optional step. Exceptions are summarized with safe reason codes, avoiding raw
transport messages in persisted output.

## Trace and replay

```python
from pathlib import Path
from preflight_agent.llm import ScriptedModel
from preflight_agent.runner import run

trace = run(
    "candidate-001",
    Path("examples/clean"),
    Path("traces"),  # must be outside the candidate directory
    model=ScriptedModel(),
)
print(trace["final_draft"]["decision"])
```

The input identity binds snapshot contents, exact YAML bytes, engine contract
version, and model identity. Each step records a cumulative input digest, output,
status, and reason codes. The advisory receipt hashes its verified inputs, full
message list, and normalized completion envelope; a separate digest seals the
receipt. The trace has its own SHA-256 integrity digest. Canonical JSON uses
sorted keys and no timestamps or absolute machine paths.

Same workflow ID + same inputs returns the saved trace exactly, without a second
model call. Same ID + changed input raises `ReplayMismatch`. Changing evidence,
workflow bytes, or model identity counts as changed input. Corrupt traces fail
closed with `TraceCorrupt`. Failed completed runs are also replayed; use a new ID
to intentionally retry. Writes are limited to the explicitly selected trace
store, with exclusive atomic publication to avoid overwriting existing traces.

## Optional OpenAI-compatible HTTP backend

This is opt-in. It was tested with a fake HTTP opener, not a live provider.
Set these environment variables outside source files:

```bash
export PREFLIGHT_BACKEND=http
export PREFLIGHT_ENDPOINT=http://localhost:11434/v1/chat/completions
export PREFLIGHT_MODEL=your-installed-model-name
```

`localhost` is the **local default** for Ollama's compatible API. The adapter also
allows `127.0.0.1` and IPv6 loopback for local HTTP. Remote endpoints require
HTTPS. For OpenAI, set `PREFLIGHT_ENDPOINT` to
`https://api.openai.com/v1/chat/completions` and supply `PREFLIGHT_API_KEY` through
the environment. Set `PREFLIGHT_MODEL` to a model identifier echoed exactly by
the provider; aliases resolved to another identifier are refused. Use a model
that supports the supplied chat parameters and JSON response instructions.

Call `run()` without an explicit model to use environment selection. Unset
`PREFLIGHT_BACKEND` defaults to scripted. The demo intentionally stays offline.
The HTTP adapter has a 30-second timeout, bounded response reads, no redirects,
no streaming, and no retries. API keys never enter receipts or trace identity.
Using HTTP transmits the bounded candidate snapshot to the selected endpoint;
only use evidence you intend to share with that provider.

## Limitations

- This is an orchestration and boundary-design sample, not a security sandbox.
  The registry's Python implementations and YAML policy are trusted. Result
  checks cannot stop a malicious Python tool from performing side effects before
  returning. An OS sandbox would be needed for hostile plugins.
- Rules use filenames and supplied summaries. They do not compute semantic API
  diffs, validate migrations, verify report authenticity, or assess vulnerabilities.
- Local SHA-256 receipts detect accidental edits, not tampering by someone who
  can replace data and recompute hashes. There are no signatures or access controls.
- Completed runs replay; there is no partial-run resume or distributed lock.
  Concurrent first runs may both call the model before exclusive trace publication.
- The candidate tree is expected to remain stable while read. This sample is not
  hardened against concurrent filesystem replacement. Keep the trace directory
  trusted and separate from evidence.
- The offline scripted model demonstrates the interface, not measured AI quality.
  No live provider compatibility or model safety claim is made.

MIT licensed. No production credentials or private source material are included.
