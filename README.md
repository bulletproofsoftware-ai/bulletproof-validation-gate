# bulletproof-validation-gate

**A Claude Code Stop hook that refuses unverified "done" claims — an adversarial verifier for completion.**

AI coding assistants love to say "Done!", "Fixed!", "All working!" — often without
actually showing you the evidence. `bulletproof-validation-gate` is a Claude Code
**Stop hook** that intercepts those claims and routes them to a local model whose only
job is to **disprove** them. If the claim lacks user-observable evidence, the turn is
**blocked** and the assistant is forced to re-engage and produce proof.

It runs entirely locally via [Ollama](https://ollama.com) — no API cost, nothing leaves
your machine.

## How it works

1. On every turn end (the `Stop` hook), it scans the assistant's final message for
   completion language (`done`, `fixed`, `resolved`, `deployed`, `working`, …).
2. If matched, it sends the claim to a local verifier model with an **adversarial**
   prompt: *find evidence this claim is unsupported — do NOT confirm, disprove.*
3. A claim **PASSES** only if it has a concrete subject, cites observable evidence
   (file paths, command output, URLs, timestamps, test results), and the evidence
   matches the claim — or it explicitly marks itself "pending verification."
4. On **FAIL**, the hook returns `{"decision":"block","reason":"…"}`, which Claude Code
   surfaces so the assistant must produce the missing evidence before finishing.

The verdict is logged; an optional notification hook can fire on failures.

## Install

1. Install [Ollama](https://ollama.com) and pull a verifier model:
   ```bash
   ollama pull llama3.2:3b     # fast; larger models (e.g. qwen) judge more accurately
   ```
2. Wire the hook into `~/.claude/settings.json` (run `./install.sh` to print the
   snippet with the absolute path filled in):
   ```json
   "Stop": [
     { "hooks": [{ "type": "command",
       "command": "python3 /absolute/path/to/completion_claim_gate.py",
       "timeout": 35000 }] }
   ]
   ```

That's it — the next time Claude claims "done" without evidence, the gate blocks it.

## Configuration (all optional, via env)

| Var | Default | Purpose |
|-----|---------|---------|
| `OLLAMA_URL` | `http://localhost:11434/api/generate` | Ollama endpoint |
| `OLLAMA_VERIFIER_MODEL` | `llama3.2:3b` | Verifier model. Bigger = better judgment. |
| `OLLAMA_VERIFIER_TIMEOUT_S` | `20` | Per-call timeout |
| `OLLAMA_VERIFIER_KEEP_ALIVE` | `24h` | Keep the model warm |
| `VALIDATION_GATE_VERDICT_DIR` | `~/.claude/validation-gate/verdicts` | Where verdicts are logged |
| `VALIDATION_GATE_LOG` | `~/.claude/validation-gate/gate.log` | Gate log file |
| `VALIDATION_GATE_NOTIFY` | *(unset)* | Optional script to run on FAIL (args: `error <subject> <body>`) |

### Swapping the backend

The verifier is a single `/api/generate` call. To use a different model, just set
`OLLAMA_VERIFIER_MODEL`. To use a different provider, point `OLLAMA_URL` at any
Ollama-compatible endpoint.

## Tuning

- **Too strict?** Small models (3B) err toward blocking. Use a larger model for more
  balanced judgment.
- **Fail-open:** if Ollama is unreachable or times out, the gate does **not** block
  (it degrades gracefully rather than wedging your session).
- **Loop protection:** the gate never blocks a turn that was itself triggered by a
  prior block (`stop_hook_active`), so you can't get stuck.

## Test

```bash
./tests/test_gate.sh     # requires Ollama running for the blocking test
```

## License

Apache-2.0 © 2026 bulletproofsoftware-ai. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
