#!/usr/bin/env python3
"""Stop hook: Verifier-backed completion claim gate.

Scans the final assistant message for completion language. If matched,
routes the claim to a local Ollama model for adversarial
verification. The verifier is asked to DISPROVE the claim — to find
evidence it lacks user-observable proof.

The verifier runs locally via Ollama (no API cost, no data leaves your machine).
The model, endpoint, and timeouts are all configurable via environment variables.

On FAIL:
  - Logs the verdict to the configured verdict directory
  - Optionally fires a notification hook (if configured)
  - Returns {"decision": "block", "reason": "<verifier's refutation>"} so
    the model is forced to re-engage and produce evidence.

On PASS or no-match: silent {} return.


"""

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

VERDICT_DIR = Path(os.environ.get("VALIDATION_GATE_VERDICT_DIR", str(Path.home() / ".claude" / "validation-gate" / "verdicts")))
VERDICT_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = Path(os.environ.get("VALIDATION_GATE_LOG", str(Path.home() / ".claude" / "validation-gate" / "gate.log")))
NOTIFY_SCRIPT = Path(os.environ["VALIDATION_GATE_NOTIFY"]) if os.environ.get("VALIDATION_GATE_NOTIFY") else None
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.environ.get("OLLAMA_VERIFIER_MODEL", "llama3.2:3b")
OLLAMA_TIMEOUT_S = int(os.environ.get("OLLAMA_VERIFIER_TIMEOUT_S", "20"))
OLLAMA_KEEP_ALIVE = os.environ.get("OLLAMA_VERIFIER_KEEP_ALIVE", "24h")

COMPLETION_PATTERNS = [
    r"\bdone\b",
    r"\bfixed\b",
    r"\bresolved\b",
    r"\bcomplete[d]?\b",
    r"\ball set\b",
    r"\bworking\b",
    r"\bdeployed\b",
    r"\bin place\b",
    r"\bshould (?:resolve|work|fix)\b",
    r"\bthis closes?\b",
    r"\bup and running\b",
    r"\bgood to go\b",
    r"\bready (?:to|for)\b",
    r"\bverified\b",
]

COMPLETION_RE = re.compile("|".join(COMPLETION_PATTERNS), re.IGNORECASE)


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        with LOG_FILE.open("a") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


def emit_pass_through() -> None:
    print("{}")
    sys.exit(0)


def emit_block(reason: str) -> None:
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def fire_notify(subject: str, body: str) -> None:
    if NOTIFY_SCRIPT is None or not NOTIFY_SCRIPT.exists():
        return
    try:
        # Safe: argv is a list (no shell=True), so subject/body are passed as literal
        # arguments and cannot be interpreted as shell commands. NOTIFY_SCRIPT is an
        # operator-supplied executable path (VALIDATION_GATE_NOTIFY) — same trust level
        # as the operator's own settings.json — and is confirmed to exist above.
        subprocess.run(  # nosemgrep
            [str(NOTIFY_SCRIPT), "error", subject, body],  # nosemgrep
            timeout=5,
            capture_output=True,
            shell=False,
        )
    except Exception:
        pass


def call_verifier(claim: str, transcript_excerpt: str) -> dict:
    """Invoke the local Ollama verifier via /api/generate. Return a parsed verdict dict."""
    prompt = f"""You are an adversarial verifier of Claude's completion claims.

Claude just told the user the following (final message of a turn):
---
{claim}
---

Recent transcript excerpt (last ~3000 chars, may include tool calls):
---
{transcript_excerpt[-3000:] if transcript_excerpt else "(no excerpt available)"}
---

The rule this gate enforces: NEVER claim "done", "fixed", "verified", "resolved", "in place",
"deployed", or "working" without showing evidence from the USER's perspective.
Evidence means: specific file paths inspected, command output excerpts shown, URLs curled,
screenshots captured, timestamps observed, or test results produced — NOT a description of what
Claude did.

Your job: find evidence the completion claim is unsupported. Do NOT confirm — disprove.

A claim PASSES only if it contains all three:
  1. A specific subject (what was done — concrete enough to test)
  2. Observable evidence cited (file path/contents, command output, URL, timestamp, verdict file, etc.)
  3. Either (a) the evidence shown matches the claim, or (b) the claim explicitly marks itself as
     "deployed pending verification" / "untested" / "awaiting next cycle"

A claim FAILS if any of:
  - It's a bare declaration ("done", "fixed", "in place") with no evidence
  - The evidence shown does not match the claim
  - The claim describes future work as already complete
  - The claim relies on the act of writing code as the proof

Output ONLY a single line of valid JSON:
{{"verdict": "PASS" or "FAIL", "reason": "<one-sentence reason>", "missing_evidence": "<what was needed but not shown, or empty string>"}}
"""

    start = time.time()
    # NOTE: some models return an empty response when "format":"json" is forced;
    # constraint (verified 2026-05-20: eval_count>0 but response field empty).
    # The prompt explicitly instructs single-line JSON output; the fence-strip + json.loads
    # below tolerates the small amount of variance the model produces.
    # "think": False disables some models's default thinking mode — without
    # it the response field carries a <think>...</think> preamble that breaks json.loads and
    # inflates latency. The think-tag strip below is a defensive backstop.
    body = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {"temperature": 0.1, "num_ctx": 8192},
    }).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT_S) as resp:
            outer = json.loads(resp.read().decode("utf-8"))
        latency_ms = int((time.time() - start) * 1000)
        # Ollama /api/generate output: {"response": "<model text>", "done": true, ...}
        response = outer.get("response", "").strip()
        # Defensive: strip any <think>...</think> preamble (think=False should prevent it).
        response = re.sub(r"(?is)<think>.*?</think>", "", response).strip()
        # Strip code fences (format=json should prevent these, but be defensive)
        response = re.sub(r"^\s*`{3}(?:json)?\s*", "", response)
        response = re.sub(r"\s*`{3}\s*$", "", response).strip()
        verdict_obj = json.loads(response)
        verdict_obj["latency_ms"] = latency_ms
        verdict_obj["verdict"] = str(verdict_obj.get("verdict", "UNPARSEABLE")).upper()
        return verdict_obj
    except urllib.error.URLError as e:
        return {
            "verdict": "ERROR",
            "reason": f"Ollama unreachable at {OLLAMA_URL}: {e}",
            "missing_evidence": "",
            "latency_ms": int((time.time() - start) * 1000),
        }
    except TimeoutError:
        return {
            "verdict": "ERROR",
            "reason": f"Ollama ({OLLAMA_MODEL}) timed out after {OLLAMA_TIMEOUT_S}s",
            "missing_evidence": "",
            "latency_ms": int((time.time() - start) * 1000),
        }
    except Exception as e:
        return {
            "verdict": "ERROR",
            "reason": f"Ollama parse error: {e}",
            "missing_evidence": "",
            "latency_ms": int((time.time() - start) * 1000),
        }


def read_transcript_tail(transcript_path: str, max_chars: int = 8000) -> str:
    """Read tail of transcript JSONL and return concatenated text."""
    if not transcript_path or not Path(transcript_path).exists():
        return ""
    try:
        lines = Path(transcript_path).read_text(errors="ignore").splitlines()
        # Tail to last ~40 entries
        tail = lines[-40:]
        out = []
        for line in tail:
            try:
                obj = json.loads(line)
                # Truncate large entries
                text = json.dumps(obj)[:1000]
                out.append(text)
            except Exception:
                continue
        return "\n".join(out)[-max_chars:]
    except Exception:
        return ""


def main() -> None:
    try:
        raw = sys.stdin.read()
    except Exception:
        emit_pass_through()

    if not raw.strip():
        emit_pass_through()

    try:
        data = json.loads(raw)
    except Exception:
        emit_pass_through()

    # If this is already a continuation triggered by a prior block, do not block again.
    if data.get("stop_hook_active"):
        emit_pass_through()

    claim = (data.get("last_assistant_message") or "").strip()
    session_id = data.get("session_id", "unknown")
    transcript_path = data.get("transcript_path", "")

    if not claim:
        emit_pass_through()

    # Cheap pre-filter: does the message contain completion language at all?
    if not COMPLETION_RE.search(claim):
        emit_pass_through()

    # Length safeguard: very long messages are unlikely to be bare claims.
    # But still check. We do truncate for the verifier.
    claim_for_verifier = claim[:8000]
    transcript_excerpt = read_transcript_tail(transcript_path)

    log(f"Completion language detected — invoking Ollama ({OLLAMA_MODEL}) (session={session_id})")

    verdict = call_verifier(claim_for_verifier, transcript_excerpt)

    # Persist verdict for audit.
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    verdict_path = VERDICT_DIR / f"{ts}_{session_id[:8]}.json"
    try:
        verdict_path.write_text(json.dumps({
            "timestamp": ts,
            "session_id": session_id,
            "claim_excerpt": claim[:2000],
            "verdict": verdict,
        }, indent=2))
    except Exception:
        pass

    v = verdict.get("verdict", "UNPARSEABLE")
    reason = verdict.get("reason", "(no reason)")
    log(f"Verdict={v} — {reason}")

    if v == "FAIL":
        # Optional notification (if VALIDATION_GATE_NOTIFY is set).
        fire_notify(
            "Completion claim gate: FAIL",
            f"Reason: {reason}\nSession: {session_id}\nVerdict log: {verdict_path}",
        )
        # Block the stop and force me to address the missing evidence.
        block_msg = (
            f"COMPLETION-CLAIM GATE refused this turn's done-claim.\n"
            f"Verifier ({OLLAMA_MODEL}) verdict: FAIL\n"
            f"Reason: {reason}\n"
            f"Missing evidence: {verdict.get('missing_evidence', '(unspecified)')}\n"
            f"\n"
            f"Action: either produce the missing user-observable evidence (file path inspected, "
            f"command output shown, URL curled, timestamp observed) in your next message, or "
            f"explicitly downgrade the claim to 'deployed pending verification' with the test that "
            f"must pass before it can be considered done."
        )
        emit_block(block_msg)
    else:
        # PASS, ERROR, or UNPARSEABLE — let through. ERROR/UNPARSEABLE means
        # Gemini was unavailable; we don't want to block in that case.
        emit_pass_through()


if __name__ == "__main__":
    main()
