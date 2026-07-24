# How to use

Once the hook is installed (see [INSTALL.md](INSTALL.md)) and Ollama is running, the
gate works automatically on every turn. You do not invoke it directly — Claude Code
fires it on the `Stop` event and honors its block/pass response.

## The lifecycle of a turn

1. The assistant finishes a turn. Claude Code sends the `Stop` payload to the gate on
   stdin.
2. The gate reads `last_assistant_message`. If it contains **no completion language**,
   the gate returns `{}` and the turn ends normally — you see nothing.
3. If it **does** contain completion language, the gate sends the claim plus a transcript
   tail to the Ollama verifier and waits for a verdict.
4. **PASS / ERROR / unparseable** → the turn is allowed through.
5. **FAIL** → the gate returns `{"decision":"block","reason":"…"}`. Claude Code surfaces
   the refutation and the assistant is forced to continue and produce evidence.

## What a block looks like

When a claim fails, the assistant receives a message like:

```
COMPLETION-CLAIM GATE refused this turn's done-claim.
Verifier (llama3.2:3b) verdict: FAIL
Reason: <one-sentence refutation from the verifier>
Missing evidence: <what was needed but not shown>

Action: either produce the missing user-observable evidence (file path inspected,
command output shown, URL curled, timestamp observed) in your next message, or
explicitly downgrade the claim to 'deployed pending verification' with the test that
must pass before it can be considered done.
```

The assistant then re-engages: it inspects a file and shows the contents, runs a command
and pastes the output, curls a URL, or explicitly downgrades the claim.

## How to make a claim that PASSES

A claim passes only if it satisfies all three of the verifier's PASS conditions:

1. **A specific, testable subject** — *what* was done, concrete enough to check. Not
   "everything works" but "the `/health` endpoint returns 200".
2. **Cited observable evidence** — a file path you inspected and its contents, a command
   and its output, a URL you curled and the status, a timestamp, a verdict file, a test
   result. Describing what you *did* is not evidence; showing the *result* is.
3. **Evidence that matches the claim** — the output actually demonstrates the claimed
   outcome. (Or the claim explicitly marks itself *pending verification* /
   *untested* / *awaiting next cycle*.)

**Fails** on any of: a bare declaration (`done`, `fixed`, `in place`) with no evidence;
evidence that does not match the claim; future work described as already complete; or
"I wrote the code" offered as the proof.

### Examples

**Fails** — bare declaration, no evidence:

> Done. The login bug is fixed and everything is working now.

**Passes** — subject + matching, observable evidence:

> Fixed the login redirect. `curl -sI localhost:3000/login` now returns
> `HTTP/1.1 200` (was 500). The failing test `test_login_redirect` passes:
> `pytest -q tests/test_login.py` → `1 passed in 0.42s`.

**Passes** — explicitly downgraded when evidence isn't available yet:

> Deployed the config change, pending verification. I could not reach the staging host
> from here; the test that must pass before this is "done" is
> `curl -sf https://staging/health` returning 200.

## Completion language that triggers the gate

The gate pre-filters on these patterns (case-insensitive, word-boundary): `done`,
`fixed`, `resolved`, `complete`/`completed`, `all set`, `working`, `deployed`,
`in place`, `should resolve`/`should work`/`should fix`, `this closes`,
`up and running`, `good to go`, `ready to`/`ready for`, `verified`.

If your final message contains none of these, the verifier is never called (fast path).

## Tuning strictness

- **Too strict?** Small models (3B) tend to err toward blocking. Point the gate at a
  larger, more capable model for more balanced judgment:
  ```bash
  export OLLAMA_VERIFIER_MODEL=qwen2.5:7b
  ```
- **Too slow?** A smaller model or a warmer cache helps. The gate sets
  `keep_alive` (default `24h`) so the model stays resident between calls. Raise the
  per-call timeout if larger models need more time (and raise the hook `timeout` in
  `settings.json` to match).
- **Fail-open by design.** If Ollama is unreachable or times out, the gate does **not**
  block — it degrades gracefully rather than wedging your session. This means: if you
  want the gate to actually enforce, keep Ollama running.
- **Loop protection.** A turn triggered by a prior block (`stop_hook_active`) is never
  blocked again, so you cannot get stuck in a block loop.

## Inspecting verdicts

Every verifier invocation writes a verdict file and a log line. To review recent
verdicts:

```bash
ls -t ~/.claude/validation-gate/verdicts | head
cat ~/.claude/validation-gate/verdicts/<latest>.json
tail ~/.claude/validation-gate/gate.log
```

See [ADMINISTRATOR.md](ADMINISTRATOR.md#verdict-logging-and-audit) for the verdict file
format and log semantics.

## Testing the gate manually

You can feed the gate a synthetic `Stop` payload to see its behavior without waiting for
a real turn:

```bash
# Pass-through (no completion language):
echo '{"last_assistant_message":"Here is the plan."}' | python3 completion_claim_gate.py

# Block (Ollama must be running; bare claim):
echo '{"last_assistant_message":"Done. Everything is fixed and working."}' \
  | python3 completion_claim_gate.py
```

Or run the bundled smoke test: `./tests/test_gate.sh`.

---

Apache-2.0 © 2026 bulletproofsoftware-ai. See [LICENSE](../LICENSE) and [NOTICE](../NOTICE).
