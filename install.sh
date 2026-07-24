#!/usr/bin/env bash
# Print the Claude Code settings.json Stop-hook snippet with the absolute path resolved.
set -euo pipefail
GATE="$(cd "$(dirname "$0")" && pwd)/completion_claim_gate.py"
cat <<JSON
Add this to the "hooks" section of your ~/.claude/settings.json:

  "Stop": [
    { "hooks": [{ "type": "command",
      "command": "python3 $GATE",
      "timeout": 35000 }] }
  ]

Requires Ollama running locally with a verifier model, e.g.:
  ollama pull llama3.2:3b
Configure via env (optional):
  OLLAMA_URL, OLLAMA_VERIFIER_MODEL, OLLAMA_VERIFIER_TIMEOUT_S,
  VALIDATION_GATE_VERDICT_DIR, VALIDATION_GATE_LOG, VALIDATION_GATE_NOTIFY
JSON
