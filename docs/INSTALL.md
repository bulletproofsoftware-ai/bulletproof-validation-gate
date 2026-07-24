# Install

`bulletproof-validation-gate` is a single Python script wired into Claude Code as a
`Stop` hook. There is **nothing to `pip install`** — the script imports only the Python
standard library. The only runtime requirement is a local [Ollama](https://ollama.com)
serving a verifier model.

## Requirements

| Requirement | Notes |
|-------------|-------|
| **Python 3.8+** | CPython. Invoked as `python3`; no packages required. |
| **Claude Code** | The host that fires the `Stop` hook and honors `{"decision":"block"}`. |
| **Ollama** | Local model server. Provides the adversarial verifier. Optional at install time, but the gate only *blocks* when Ollama is reachable (it fails open otherwise). |

There is no Docker image, no compose stack, and no lockfile — by design, so the gate
runs reliably inside a hook with no environment setup.

## 1. Install Ollama and pull a verifier model

Install Ollama from <https://ollama.com>, then pull a model:

```bash
ollama pull llama3.2:3b     # fast; good default
# larger models judge more accurately, e.g.:
# ollama pull qwen2.5:7b
```

The default model is `llama3.2:3b`. Bigger models give more balanced judgment (small
3B models err toward blocking); see [HOW-TO-USE.md](HOW-TO-USE.md#tuning-strictness).

Confirm Ollama is serving:

```bash
curl -s http://localhost:11434/api/tags | head -c 200
```

## 2. Get the script

Clone the repository (or copy `completion_claim_gate.py` anywhere stable — the hook
references it by **absolute path**, so it must not move afterward):

```bash
git clone https://github.com/bulletproofsoftware-ai/bulletproof-validation-gate.git
cd bulletproof-validation-gate
```

## 3. Wire the hook into Claude Code

Run the installer to print the exact snippet with the absolute path already filled in:

```bash
./install.sh
```

It prints something like:

```
  "Stop": [
    { "hooks": [{ "type": "command",
      "command": "python3 /absolute/path/to/bulletproof-validation-gate/completion_claim_gate.py",
      "timeout": 35000 }] }
  ]
```

Add that `"Stop"` array to the `"hooks"` section of your `~/.claude/settings.json`. If
you prefer to copy a file, `settings.snippet.json` contains the same structure with a
placeholder path — replace `/absolute/path/to/...` with the real absolute path to
`completion_claim_gate.py`.

> **Timeout.** The hook `timeout` is `35000` ms. This must exceed the verifier call
> timeout (`OLLAMA_VERIFIER_TIMEOUT_S`, default `20`s) with headroom for model load. If
> you raise the verifier timeout, raise the hook timeout to match.

## 4. Verify the install

Run the smoke test (test 3 requires Ollama running):

```bash
./tests/test_gate.sh
```

Expected:

- **test 1** — empty input passes through (`{}`): **PASS**
- **test 2** — a message with no completion language passes through: **PASS**
- **test 3** — a bare `"Done. Everything is fixed and working."` claim is **BLOCKED**:
  **PASS (blocked)** when Ollama is up; **SKIP/FAIL** if Ollama is down (the gate fails
  open, so no block is emitted).

You can also drive the gate directly to confirm the pass-through path without Ollama:

```bash
echo '{"last_assistant_message":"Here is the plan for the next step."}' \
  | python3 completion_claim_gate.py
# -> {}   (no completion language, passes through)
```

And confirm the block path (Ollama must be running):

```bash
echo '{"last_assistant_message":"Done. Everything is fixed and working."}' \
  | python3 completion_claim_gate.py
# -> {"decision": "block", "reason": "..."}
```

## 5. (Optional) configuration

All configuration is via environment variables — none are required. See
[ADMINISTRATOR.md](ADMINISTRATOR.md#configuration-environment-variables) for the full
table (model, endpoint, timeouts, verdict/log locations, and the optional FAIL
notification script).

## Uninstall

Remove the `"Stop"` entry you added to `~/.claude/settings.json`. Optionally delete the
verdict/log directory (default `~/.claude/validation-gate/`). Nothing else is installed
system-wide.

---

Apache-2.0 © 2026 bulletproofsoftware-ai. See [LICENSE](../LICENSE) and [NOTICE](../NOTICE).
