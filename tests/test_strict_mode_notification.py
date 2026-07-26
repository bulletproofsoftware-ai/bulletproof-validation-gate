"""Round-2 adversarial review regression (validation-gate).

Corroborated HIGH (completion_claim_gate.py:341): when the verifier could not
produce a verdict, fire_notify() ran before the STRICT_MODE branch and always said
the gate "let the turn through because VALIDATION_GATE_STRICT is not set" — even
when STRICT_MODE was set and emit_block() blocked the turn microseconds later.
The only out-of-band record of a strict-mode block described the opposite outcome.

The gate reads its configuration from the environment at import time, so each case
runs the real script as a subprocess with a stub notify executable.

Run:  pytest tests/test_strict_mode_notification.py -v
  or: python3 tests/test_strict_mode_notification.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

GATE = Path(__file__).resolve().parent.parent / "completion_claim_gate.py"

# Port 1 is reserved and never listening, so call_verifier() fails and the gate
# takes its ERROR/UNPARSEABLE branch — the branch the finding is in.
UNREACHABLE_OLLAMA = "http://127.0.0.1:1/api/generate"

BARE_CLAIM = json.dumps(
    {"last_assistant_message": "Done. Everything is fixed and working."}
)


def run_gate(*, strict: bool, tmp_path: Path) -> tuple[dict, str]:
    """Run the gate with the verifier unreachable. Returns (hook output, notify body)."""
    notify_log = tmp_path / "notify.log"
    notify_script = tmp_path / "notify.sh"
    notify_script.write_text(
        "#!/usr/bin/env bash\n"
        f'printf "%s\\n" "$3" > "{notify_log}"\n'
    )
    notify_script.chmod(0o755)

    env = {
        **os.environ,
        "VALIDATION_GATE_VERDICT_DIR": str(tmp_path / "verdicts"),
        "VALIDATION_GATE_LOG": str(tmp_path / "gate.log"),
        "VALIDATION_GATE_NOTIFY": str(notify_script),
        "OLLAMA_URL": UNREACHABLE_OLLAMA,
        "OLLAMA_VERIFIER_TIMEOUT_S": "2",
    }
    if strict:
        env["VALIDATION_GATE_STRICT"] = "1"
    else:
        env.pop("VALIDATION_GATE_STRICT", None)

    proc = subprocess.run(
        [sys.executable, str(GATE)],
        input=BARE_CLAIM,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr

    output = json.loads(proc.stdout or "{}")
    body = notify_log.read_text() if notify_log.exists() else ""
    assert body, "the gate must notify when the verifier is unavailable"
    return output, body


@pytest.fixture()
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


def test_strict_mode_blocks_and_says_so(tmp_dir):
    output, body = run_gate(strict=True, tmp_path=tmp_dir)

    assert output.get("decision") == "block", output
    assert "BLOCKED" in body, body
    assert "let the turn through" not in body, body


def test_permissive_mode_passes_through_and_says_so(tmp_dir):
    output, body = run_gate(strict=False, tmp_path=tmp_dir)

    assert output.get("decision") != "block", output
    assert "let the turn through" in body, body
    assert "BLOCKED" not in body, body


def test_notification_matches_the_decision_in_both_modes(tmp_dir):
    """The property the finding violated: the message the operator receives has to
    describe what the gate actually did."""
    for strict in (True, False):
        sub = tmp_dir / f"strict-{strict}"
        sub.mkdir()
        output, body = run_gate(strict=strict, tmp_path=sub)
        blocked = output.get("decision") == "block"
        claims_blocked = "BLOCKED" in body
        assert blocked == claims_blocked, (
            f"strict={strict}: gate blocked={blocked} but notification said "
            f"blocked={claims_blocked}\nbody: {body}"
        )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
