# Software Bill of Materials (SBOM)

This document is the human-readable summary of the machine-readable CycloneDX SBOM at
[`bulletproof-validation-gate.cyclonedx.json`](bulletproof-validation-gate.cyclonedx.json)
(CycloneDX 1.5).

## Summary

| Metric | Value |
|--------|-------|
| Distributable components (third-party) | **0** |
| Third-party runtime dependencies | **0** |
| Third-party dev/test dependencies | **0** |
| Dependency manifests present | none (`requirements.txt`, `pyproject.toml`, `setup.py`, lockfiles are all absent) |
| Language / runtime | Python (CPython) ≥ 3.8 |
| Container base images | none (no `Dockerfile`, no compose stack) |
| License | Apache-2.0 |

**`bulletproof-validation-gate` has no third-party dependencies.** The entire tool is a
single script — `completion_claim_gate.py` — that imports only the Python **standard
library**. This is by design: the gate must run reliably inside a Claude Code `Stop`
hook with no `pip install` step, no virtualenv, and nothing that could drift or break a
user's session. The `components` array in the CycloneDX file is therefore intentionally
empty; the standard library ships with the CPython interpreter and is not a
separately-distributed package.

## Standard-library modules used

These are part of CPython and are **not** external dependencies — they are listed for
transparency about the tool's surface area:

| Module | Purpose in the gate |
|--------|---------------------|
| `json` | Parse the hook's stdin payload; build the block/pass response; parse the verifier's verdict |
| `os` | Read configuration from environment variables |
| `re` | Match completion-language patterns; strip `<think>` tags and code fences from model output |
| `subprocess` | Fire the optional notification script on a FAIL verdict |
| `sys` | Read stdin, write the hook response, exit |
| `time` | Measure verifier latency |
| `urllib.request` / `urllib.error` | POST the claim to the local Ollama `/api/generate` endpoint |
| `datetime` | UTC timestamps for the log and verdict filenames |
| `pathlib` | Resolve and create the verdict/log directories |

## External runtime requirement (not a Python package)

The gate calls a local **Ollama** endpoint (default `http://localhost:11434/api/generate`)
to run the adversarial verifier model (default `llama3.2:3b`). Ollama and the model are
installed and run by the operator **outside** this repository — they are a network
service, not a Python dependency, and so do not appear in the SBOM as components. If
Ollama is unreachable, the gate fails **open** (does not block); see
[ADMINISTRATOR.md](ADMINISTRATOR.md).

## Test / CI tooling

`tests/test_gate.sh` is a POSIX shell smoke test that shells out to `python3` and `curl`
— it introduces no Python packages. The GitHub Actions workflow (`.github/workflows/ci.yml`)
optionally installs `pytest` **only if** a `tests` directory or `test_*.py` files are
present; this repo ships shell tests, so no PyPI package is installed by CI for this repo.
These are build-time conveniences, not shipped dependencies.

## Regenerating this SBOM

Because there are no manifests to resolve, the SBOM is maintained by hand and verified by
inspecting the imports:

```bash
grep -nE '^\s*(import|from)\s' completion_claim_gate.py
# Every module listed must be a Python standard-library module.
```

If a third-party dependency is ever added, install it and regenerate a real CycloneDX
document (e.g. with `cyclonedx-py` or `syft`) and replace the hand-maintained file.

---

Apache-2.0 © 2026 bulletproofsoftware-ai. See [LICENSE](../LICENSE) and [NOTICE](../NOTICE).
