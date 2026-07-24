# Overview

`bulletproof-validation-gate` is a single-file **Claude Code `Stop` hook** that
adversarially verifies completion claims. When an AI coding assistant ends a turn with
language like *"Done"*, *"Fixed"*, *"All working"*, the gate intercepts that final
message and routes it to a **local model whose only job is to disprove the claim**. If
the claim lacks user-observable evidence, the turn is **blocked** and the assistant is
forced to re-engage and produce proof.

Everything runs **locally** through [Ollama](https://ollama.com): no API cost, and
nothing leaves the machine.

## Why it exists

AI assistants routinely declare success without showing evidence. "Done!" is cheap;
proof is not. The result is a stream of unverified completion claims that a human then
has to QA by hand. This gate moves that check to the moment the claim is made — before
the turn is allowed to finish — and it does so with an **adversarial** verifier that is
prompted to *find reasons the claim is unsupported*, not to rubber-stamp it.

## What it does, concretely

1. **Pre-filter (cheap, regex).** On every `Stop` event, the gate scans the assistant's
   final message for completion language: `done`, `fixed`, `resolved`, `complete[d]`,
   `all set`, `working`, `deployed`, `in place`, `should (resolve|work|fix)`,
   `this closes`, `up and running`, `good to go`, `ready to/for`, `verified`. If none
   match, the turn passes through silently (`{}`).

2. **Adversarial verification (local model).** If completion language is present, the
   claim — plus a tail of the session transcript — is sent to the Ollama verifier with a
   prompt that instructs it to **disprove** the claim. A claim **PASSES** only if it has
   all three of: a concrete subject, cited observable evidence (file paths, command
   output, URLs, timestamps, test results), and evidence that matches the claim — or it
   explicitly marks itself *pending verification*.

3. **Enforcement.** On `FAIL`, the hook returns
   `{"decision":"block","reason":"…"}`; Claude Code surfaces the refutation and the
   assistant must produce the missing evidence before finishing. On `PASS`, `ERROR`, or
   an unparseable verdict, the turn is allowed through.

4. **Audit.** Every invocation writes a verdict JSON file and appends a log line.

## The verdict contract

The verifier is asked to emit exactly one line of JSON:

```json
{"verdict": "PASS" | "FAIL", "reason": "<one sentence>", "missing_evidence": "<what was needed, or empty>"}
```

- **PASS** requires: (1) a specific, testable subject; (2) observable evidence cited;
  (3) the evidence matches the claim **or** the claim is explicitly marked
  "pending verification" / "untested" / "awaiting next cycle".
- **FAIL** on any of: a bare declaration with no evidence; evidence that does not match
  the claim; future work described as already complete; or "I wrote the code" offered as
  the proof.

## Design principles

- **Fail-open, never wedge the session.** If Ollama is unreachable, times out, or
  returns something unparseable, the gate does **not** block. A verification backend
  being down must never prevent you from finishing a turn.
- **Loop-safe.** A turn that was itself triggered by a prior block
  (`stop_hook_active`) is never blocked again, so the assistant cannot get stuck in a
  block loop.
- **Zero third-party dependencies.** The entire tool imports only the Python standard
  library — no `pip install`, no virtualenv, nothing to drift. See [SBOM.md](SBOM.md).
- **Local-only and private.** The claim and transcript excerpt are sent only to the
  configured Ollama endpoint (localhost by default). No cloud calls.
- **Backend-agnostic.** The verifier is a single `/api/generate` call. Swap the model
  with `OLLAMA_VERIFIER_MODEL`, or point `OLLAMA_URL` at any Ollama-compatible endpoint.

## What it is *not*

- It is **not** a linter, test runner, or CI gate — it judges the *claim*, not the code.
- It does **not** guarantee correctness; it raises the bar for what counts as "done" by
  demanding evidence, and it is only as strict as the verifier model you point it at.
- It is **not** a network service — it is a script Claude Code executes on the `Stop`
  event.

## Repository layout

| Path | Purpose |
|------|---------|
| `completion_claim_gate.py` | The entire gate — the `Stop` hook script |
| `install.sh` | Prints the `settings.json` snippet with the absolute path filled in |
| `settings.snippet.json` | Copy-paste hook configuration (placeholder path) |
| `tests/test_gate.sh` | POSIX smoke test (pass-through + block behavior) |
| `.github/workflows/ci.yml` | CI: compile-check + optional pytest |
| `docs/` | This documentation set and the SBOM |

## Where to go next

- [INSTALL.md](INSTALL.md) — install Ollama, pull a model, wire up the hook.
- [HOW-TO-USE.md](HOW-TO-USE.md) — what blocking looks like, how to respond, tuning strictness.
- [ADMINISTRATOR.md](ADMINISTRATOR.md) — configuration, verdict logging, fail-open behavior, operations.
- [SBOM.md](SBOM.md) — dependency posture (spoiler: none).

---

Apache-2.0 © 2026 bulletproofsoftware-ai. See [LICENSE](../LICENSE) and [NOTICE](../NOTICE).
