#!/usr/bin/env bash
# Smoke test: a bare completion claim must be BLOCKED; empty input must pass through.
set -u
DIR="$(cd "$(dirname "$0")/.." && pwd)"
GATE="$DIR/completion_claim_gate.py"
export VALIDATION_GATE_VERDICT_DIR="$(mktemp -d)"

echo "== test 1: empty input passes through (returns {}) =="
OUT=$(printf '' | python3 "$GATE" 2>/dev/null)
[ "$OUT" = "{}" ] || [ -z "$OUT" ] && echo "  PASS" || echo "  FAIL: got '$OUT'"

echo "== test 2: no completion language passes through =="
OUT=$(echo '{"last_assistant_message":"Here is the plan for the next step."}' | python3 "$GATE" 2>/dev/null)
echo "$OUT" | grep -q "block" && echo "  FAIL (should not block)" || echo "  PASS"

echo "== test 3: bare 'Done' claim is BLOCKED (requires Ollama running) =="
OUT=$(echo '{"last_assistant_message":"Done. Everything is fixed and working."}' | python3 "$GATE" 2>/dev/null)
echo "$OUT" | grep -q '"decision": "block"' && echo "  PASS (blocked)" || echo "  SKIP/FAIL (Ollama down? got: $OUT)"
