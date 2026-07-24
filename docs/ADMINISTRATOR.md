# Administrator guide

This guide covers operating `bulletproof-validation-gate`: configuration, verdict
logging, the optional notification hook, tuning, and fail-open behavior.

The gate is a single stdlib-only Python script wired into Claude Code as a `Stop` hook.
It has **no service to run, no database, no container, and no scaling story** — those
sections do not apply. The only moving part it depends on is a local Ollama endpoint,
which the operator runs separately.

## Configuration (environment variables)

All configuration is via environment variables, read at process start. None are
required; every one has a default.

| Variable | Default | Purpose |
|----------|---------|---------|
| `OLLAMA_URL` | `http://localhost:11434/api/generate` | The Ollama `/api/generate` endpoint the verifier is called against. Point at any Ollama-compatible endpoint to swap providers. |
| `OLLAMA_VERIFIER_MODEL` | `llama3.2:3b` | The verifier model. Bigger models judge more accurately; small 3B models err toward blocking. |
| `OLLAMA_VERIFIER_TIMEOUT_S` | `20` | Per-call timeout, in seconds, for the verifier request. Must be comfortably below the hook `timeout` in `settings.json` (default `35000` ms). |
| `OLLAMA_VERIFIER_KEEP_ALIVE` | `24h` | Passed to Ollama as `keep_alive` so the model stays resident between turns (avoids cold-start latency). |
| `VALIDATION_GATE_VERDICT_DIR` | `~/.claude/validation-gate/verdicts` | Directory where per-invocation verdict JSON files are written. Created on start. |
| `VALIDATION_GATE_LOG` | `~/.claude/validation-gate/gate.log` | Append-only log file for gate activity. |
| `VALIDATION_GATE_NOTIFY` | *(unset)* | Optional path to an executable run on a **FAIL** verdict. Invoked as `<script> error <subject> <body>` with a 5s timeout. If unset or the path does not exist, no notification fires. |

Because these are read at process start, the hook picks up changes on the next turn (no
restart of any long-lived process — the gate runs fresh each `Stop` event). To set them
persistently, export them in the environment Claude Code runs under, or wrap the hook
command in a small launcher that exports them before calling `python3
completion_claim_gate.py`.

### Where the request goes

The verifier is a single POST to `OLLAMA_URL` with:

```json
{
  "model": "<OLLAMA_VERIFIER_MODEL>",
  "prompt": "<adversarial prompt with the claim + transcript tail>",
  "stream": false,
  "think": false,
  "keep_alive": "<OLLAMA_VERIFIER_KEEP_ALIVE>",
  "options": {"temperature": 0.1, "num_ctx": 8192}
}
```

`think: false` disables the "thinking" preamble some models emit (which would otherwise
break JSON parsing and inflate latency); a `<think>…</think>` strip and a code-fence
strip are applied defensively to the response before parsing. `temperature: 0.1` keeps
the verdict stable.

## Verdict logging and audit

Every time completion language is detected and the verifier is called, the gate persists
a verdict file:

- **Location:** `VALIDATION_GATE_VERDICT_DIR` (default
  `~/.claude/validation-gate/verdicts`).
- **Filename:** `<UTC-timestamp>_<session-id-prefix>.json`, e.g.
  `20260724T191500Z_a1b2c3d4.json`.
- **Contents:**

  ```json
  {
    "timestamp": "20260724T191500Z",
    "session_id": "<full session id>",
    "claim_excerpt": "<first 2000 chars of the assistant's final message>",
    "verdict": {
      "verdict": "PASS | FAIL | ERROR | UNPARSEABLE",
      "reason": "<one-sentence reason>",
      "missing_evidence": "<what was needed, or empty>",
      "latency_ms": 1234
    }
  }
  ```

The append-only **log** (`VALIDATION_GATE_LOG`, default
`~/.claude/validation-gate/gate.log`) records one line when completion language is
detected (which model was invoked, for which session) and one line for the resulting
verdict and reason. Both writes are best-effort and wrapped so a filesystem hiccup never
aborts the hook.

> **Retention.** Nothing prunes the verdict directory or the log; they grow with usage.
> If you care about disk, rotate or clear them on your own schedule (e.g. a periodic
> `find ~/.claude/validation-gate/verdicts -mtime +30 -delete`). The gate re-creates the
> directory as needed.

## Optional FAIL notification

Set `VALIDATION_GATE_NOTIFY` to an executable to be alerted when a claim is blocked. On
a **FAIL** verdict the gate runs:

```
<VALIDATION_GATE_NOTIFY> error "Completion claim gate: FAIL" "Reason: …\nSession: …\nVerdict log: …"
```

with a 5-second timeout and output captured (not surfaced). The call is best-effort: if
the script is missing, errors, or times out, the gate still emits its block response.
This is the seam for wiring the gate into a chat/paging notifier.

## Fail-open behavior (important)

The gate is deliberately **fail-open**: a verification-backend problem must never wedge a
session. Specifically, the turn is **allowed through** (no block) whenever:

- Ollama is unreachable at `OLLAMA_URL` (connection refused, DNS, etc.) → verdict
  `ERROR`.
- The verifier call exceeds `OLLAMA_VERIFIER_TIMEOUT_S` → verdict `ERROR`.
- The model returns output that cannot be parsed into a verdict → verdict `ERROR` /
  `UNPARSEABLE`.
- The `Stop` payload is empty, non-JSON, has no `last_assistant_message`, or the message
  contains no completion language → silent pass-through.
- The payload has `stop_hook_active: true` (this turn was itself triggered by a prior
  block) → pass-through, to prevent block loops.

Only an explicit `FAIL` verdict produces a block. The practical consequence: **the gate
only enforces while Ollama is up.** If you want guaranteed enforcement, monitor Ollama's
availability yourself — the gate will not tell you it stopped blocking (that is the point
of failing open).

## Tuning

- **Reduce false blocks:** use a larger verifier model (`OLLAMA_VERIFIER_MODEL`), which
  judges more evenly than a 3B model.
- **Reduce latency:** keep the model warm via `OLLAMA_VERIFIER_KEEP_ALIVE` (default
  `24h`); a smaller model responds faster.
- **Avoid hook timeouts:** keep `OLLAMA_VERIFIER_TIMEOUT_S` well under the
  `settings.json` hook `timeout` (default `35000` ms). If you raise one, raise the other.

## Operational checklist

- [ ] Ollama running and the verifier model pulled (`ollama list`).
- [ ] Hook wired with the correct **absolute** path (`./install.sh` prints it).
- [ ] `settings.json` hook `timeout` > `OLLAMA_VERIFIER_TIMEOUT_S`.
- [ ] Verdict/log directory writable (default under `~/.claude/validation-gate/`).
- [ ] (Optional) `VALIDATION_GATE_NOTIFY` points at a real executable.
- [ ] Smoke test passes: `./tests/test_gate.sh`.

## Security and privacy notes

- The claim text and a tail of the session transcript are sent **only** to `OLLAMA_URL`
  (localhost by default). Nothing is sent to any cloud service. If you repoint
  `OLLAMA_URL` at a remote endpoint, that transcript excerpt leaves the machine — keep it
  local unless you trust the destination.
- Verdict files contain a **2000-character excerpt** of the assistant's final message.
  Treat the verdict directory with the same sensitivity as your session transcripts.
- The optional notification script is executed with the arguments shown above; point it
  only at a trusted executable.

---

Apache-2.0 © 2026 bulletproofsoftware-ai. See [LICENSE](../LICENSE) and [NOTICE](../NOTICE).
