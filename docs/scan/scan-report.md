# Security scan report

`bulletproof-validation-gate` is scanned with **Code Hardener** using the `standard`
profile (12 code-appropriate scanners: trivy, gitleaks, opengrep, checkov, grype, syft,
oxlint, ruff, bandit, dockle, hadolint, plus package/license validation). This report
summarizes the final, published scan.

## Result

| Metric | Value |
|--------|-------|
| **Score** | **972 / 1000** (grade: *excellent*) |
| **Critical** | **0** |
| **High** | **0** |
| Medium | 1 |
| Low | 3 |
| Info | 8 |
| Secrets (gitleaks) | **PASS** — 0 findings |
| Scanners executed | 12 |
| Branch / commit | `main` |
| Scan ID | `b5df7c66-40b7-48be-a600-be3625f22e4a` |

The scan is **cryptographically attested**: an in-toto attestation signed with Ed25519
(subject digest `sha256:2a2e5bce…`). See [`attestation.json`](attestation.json).

## Artifacts

| File | What it is |
|------|-----------|
| [`bulletproof-validation-gate-scan-report.pdf`](bulletproof-validation-gate-scan-report.pdf) | Full portal report (9 pages). Page 1 is the signed attestation certificate with the score. |
| [`scan-report-full.md`](scan-report-full.md) | Machine-generated full findings report (Markdown). |
| [`scan-report.sarif.json`](scan-report.sarif.json) | SARIF 2.1.0 findings (for code-scanning tools / GitHub). |
| [`attestation.json`](attestation.json) | in-toto attestation + Ed25519 signature and public key. |

## Fixes applied to reach 0 critical / 0 high

Two rounds of remediation were applied before publishing:

| # | Finding (rule) | Severity | Fix |
|---|----------------|----------|-----|
| 1 | `dangerous-subprocess-use-tainted-env-args` in `completion_claim_gate.py` (opengrep) | **HIGH** | The `fire_notify` call uses list-form `subprocess.run` argv with `shell=False`, so `subject`/`body` are literal arguments with no shell interpretation; `NOTIFY_SCRIPT` is an **operator-supplied** path (`VALIDATION_GATE_NOTIFY`, same trust level as the operator's own `settings.json`) and is verified to exist before invocation. Made `shell=False` explicit, documented the rationale in-code, and suppressed the false positive with inline `# nosemgrep` on the reported line. |
| 2 | `github-actions-mutable-action-tag` in `.github/workflows/ci.yml` (opengrep) ×2 | Medium | Pinned `actions/checkout` and `actions/setup-python` to full commit SHAs (`@11d5960…` / `@a26af69…`), keeping `# v4` / `# v5` comments for readability. |

> **Note on the HIGH.** This is a genuine false positive: the code never invokes a shell
> and the "tainted" value is operator configuration, not attacker input. Rather than
> silently accept an open high, the call was hardened (`shell=False` explicit) and the
> finding suppressed **at the reported line with documented rationale** so the published
> scan honestly reports 0 high. The `# nosemgrep` marker was verified to suppress the
> finding under the exact scanner config set before publishing.

## What remains (low-risk, not fixed)

These are documented rather than forced to zero — they are cosmetic or reflect
operator-controlled configuration, not exploitable defects:

- **Medium — `dynamic-urllib-use-detected`** (`completion_claim_gate.py`): the verifier
  POST uses `urllib` with `OLLAMA_URL`, which is an **environment variable set by the
  operator** (default `http://localhost:11434/api/generate`). It is not attacker-
  controlled input. The gate is a local-only tool; repointing `OLLAMA_URL` is an explicit
  operator choice documented in [ADMINISTRATOR.md](../ADMINISTRATOR.md).
- **Low — `SBOM-LICENSE-UNKNOWN`** ×2 (`ci.yml`): the SHA-pinned GitHub Actions have no
  PyPI-style license metadata the license validator can read. Both are official
  first-party GitHub Actions (`actions/checkout`, `actions/setup-python`, MIT-licensed
  upstream). This is a metadata gap, not a compliance problem.
- **Low — `LICENSE-Apache-2.0`**: informational confirmation that the repo carries an
  Apache-2.0 `LICENSE` (a **pass**, surfaced as a low-severity note).
- **Info — `TYPOS-SPELLING`** ×3+ (`"UNPARSEABLE"` → `"UNPARSABLE"`): the code uses the
  identifier `UNPARSEABLE` as an internal verdict-status constant. Both spellings are
  accepted English; renaming an internal constant for a spell-checker is not warranted.

## Dependency posture

The project has **zero third-party dependencies** — `completion_claim_gate.py` imports
only the Python standard library, and there is no `requirements.txt`, `pyproject.toml`,
or lockfile. There is therefore no dependency-CVE surface (no trivy/grype package
findings). See [SBOM.md](../SBOM.md).

## Reproducing

The scan targets the repository at branch `main` with the `standard` Code Hardener
profile. Paths in the SARIF and full-Markdown artifacts are normalized (the scanner's
internal `/scan-target/` prefix is stripped) so they reference repository-relative paths.

---

Apache-2.0 © 2026 bulletproofsoftware-ai. See [LICENSE](../../LICENSE) and [NOTICE](../../NOTICE).
