# Security Policy

This document describes how to report security vulnerabilities in the **bulletproof-validation-gate** project and the response commitments of the maintainers.

## Supported Versions

| Version Range | Supported |
|---------------|-----------|
| `0.1.x` (initial release line) | Yes — receives security fixes |
| Any pre-release / branch builds | No — use only for testing |

When a new minor or major release ships, the previous minor remains supported for 90 days for security fixes only.

## Reporting a Vulnerability

**Please do NOT open a public GitHub issue for security vulnerabilities.** Public disclosure before a fix is available puts users at risk.

Send vulnerability reports to the security contact for the organization operating this deployment (`security@<your-domain>`), or open a GitHub private security advisory on this repository.

Include the following in your report:

1. **Affected component** — e.g. the transcript reader, the completion-pattern matcher, the Ollama call, the verdict logger, or the notification hook in `completion_claim_gate.py`
2. **Vulnerability class** — e.g. prompt injection, command injection, information disclosure, path traversal, denial of service
3. **Impact** — what an adversary can achieve
4. **Reproduction steps** — a minimal proof of concept
5. **Affected version(s)** — git SHA or release tag
6. **Suggested mitigation** (optional)
7. **Your contact details** — you may report anonymously, but we cannot then acknowledge or credit the report

### Response Targets

| Stage | Target |
|-------|--------|
| Acknowledge receipt | 3 business days |
| Initial severity assessment | 7 business days |
| Fix or documented mitigation for High/Critical | 30 days |
| Public advisory after fix ships | 7 days |

We ask that you allow 90 days before public disclosure, or until a fix ships, whichever comes first.

## Security Model

This is a **Claude Code `Stop` hook**. It runs on your machine, with your user's privileges, on every turn end. Understanding what it does and does not defend against matters more than usual, because it sits in the trust path of an assistant that is itself editing your code.

### What it is, and what it is not

The gate is an **advisory quality control, not a security boundary.** It exists to stop an assistant from claiming "done" without evidence. It does not sandbox the assistant, does not restrict what the assistant may do, and must not be relied on to prevent malicious action. An assistant that wants to bypass it can simply avoid completion language.

### Trust boundaries

- **Assistant transcript (input)** — the gate reads the assistant's final message and sends it to a local model. That text is **untrusted**: it may contain content the assistant copied from a web page, a dependency, or a repository file. A crafted transcript can attempt to steer the verifier's verdict (prompt injection against the judge). The consequence is bounded — the worst outcome is a wrong PASS/FAIL on a completion claim — but do not extend this component to take actions based on verifier output without re-reading this note.
- **`VALIDATION_GATE_NOTIFY` (privileged configuration)** — if set, this names an executable that the gate runs on failure. It is invoked via `subprocess.run` with an argv **list** and no `shell=True`, so the subject and body are passed as literal arguments and cannot be reinterpreted as shell commands (`completion_claim_gate.py:97`). The path itself is operator-supplied and carries the same trust level as your `settings.json`. Anyone who can set that environment variable can make the gate execute a program of their choosing — treat it as equivalent to write access to your shell profile.
- **Ollama endpoint (`OLLAMA_URL`)** — defaults to `http://localhost:11434`. The transcript is sent here. If you repoint this at a remote host, **your assistant transcripts leave your machine**, including whatever source code or secrets happen to appear in them. The default is local specifically so that nothing does.

### Failure behaviour

The gate **fails open by default**. When the verifier is unreachable or returns no usable verdict, the turn is allowed through (`completion_claim_gate.py:43-48`). This is deliberate: a control that wedges every session during an Ollama outage gets uninstalled, which is a worse outcome than a missed check. Set `VALIDATION_GATE_STRICT=1` to fail closed where an unverified completion claim is worse than an interruption. Either way the outage is logged and notified, so a dead gate is not mistaken for a clean run.

### Data at rest

- Verdicts are written to `VALIDATION_GATE_VERDICT_DIR` (default `~/.claude/validation-gate/verdicts`) and the log to `VALIDATION_GATE_LOG`. **Both contain excerpts of assistant output**, which can include file paths, code, command output, and anything else that appeared in the turn. They inherit the sensitivity of the work you do with Claude Code. Protect them with filesystem permissions and include them in your retention and deletion policy; nothing in this project prunes them for you.

### Not in scope

- The gate does not authenticate the Ollama endpoint or verify the identity of the verifier model.
- The gate does not protect against an assistant that avoids completion language, rephrases around the patterns in `COMPLETION_PATTERNS`, or simply stops mid-task.
- Verifier verdicts are model output and are **not** guaranteed correct in either direction. A PASS is not an assurance that work was actually completed.

## Security Practices in This Repository

- The project is pure standard-library Python; it adds no third-party runtime dependencies, so there is no dependency supply chain to compromise.
- The notification subprocess is invoked with an argv list and never `shell=True`.
- No credentials, private hostnames, or environment-specific endpoints are committed; every setting is an environment variable with a local-only default.
- GitHub Actions are pinned to full commit SHAs.
- CodeQL runs on push, pull request, and a weekly schedule.
