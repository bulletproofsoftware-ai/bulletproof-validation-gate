# Briefing Report: bulletproof-validation-gate Technical Overview

### 1. Executive Summary
The `bulletproof-validation-gate` is a high-reliability, standard-library-only Python implementation of a **Stop hook** for Claude Code. Its objective is to eliminate "lazy" completion claims by the AI assistant, forcing the transition from verbal declarations of success to evidence-based verification.

The system utilizes a local **adversarial verification** architecture. By routing assistant completion claims (e.g., "done," "fixed," "resolved") to a local Large Language Model (LLM) via Ollama, the gate subjects each claim to a verifier specifically prompted to disprove it. If the assistant cannot provide user-observable evidence—such as file contents, command outputs, or test results—the gate intercepts the turn and blocks the completion.

### 2. Core Mechanism and Turn Lifecycle
The gate executes automatically during the Claude Code "Stop" event. The lifecycle of a turn follows a strict four-stage pipeline:

1.  **Pre-filtering (Fast Path):** The gate performs a computationally inexpensive regex scan of the assistant’s final message. This scan is **case-insensitive** and uses **word boundaries** (`\b`) to detect specific "completion language." If no keywords are detected, the gate exits immediately with `{}` (pass).
2.  **Adversarial Verification:** If keywords match, the gate extracts the completion claim and a tail of the session transcript. This data is POSTed to the local Ollama endpoint. To ensure stability and deterministic output, the request is hardcoded with `temperature: 0.1` and `think: false` (to disable thinking preambles that complicate JSON parsing).
3.  **Enforcement:** The gate evaluates the verifier's response. A **FAIL** verdict triggers a block response: `{"decision":"block", "reason":"..."}`. This surfaces a refutation to the assistant, requiring it to re-engage. A **PASS**, **ERROR**, or unparseable response allows the turn to finish.
4.  **Audit:** The verdict, reasoning, and metadata are persisted to a JSON audit file and a central activity log for retrospective engineering review.

> **Trigger Keywords (Case-Insensitive/Word-Boundary):**
> done, fixed, resolved, complete, completed, all set, working, deployed, in place, should resolve, should work, should fix, this closes, up and running, good to go, ready to, ready for, verified.

### 3. Adversarial Validation Logic (The Verdict Contract)
The verifier model is governed by a "Verdict Contract." Unlike traditional evaluators, the verifier is explicitly instructed to act as an adversary—identifying reasons why a claim is unsupported rather than looking for reasons to approve it.

| **PASS Conditions** | **FAIL Triggers** |
| :--- | :--- |
| **Specific Subject:** Must define a concrete, testable outcome (e.g., a specific endpoint behavior or file change). | **Bare Declarations:** Simple statements like "done" or "fixed" without accompanying evidence. |
| **Cited Observable Evidence:** Inclusion of specific file paths, command outputs, URLs, timestamps, or test results. | **Mismatched Evidence:** The provided evidence does not demonstrate the success claimed (e.g., a test failure in the logs). |
| **Matching Status:** The evidence supports the claim, or the claim is explicitly marked as "pending verification" or "untested." | **Future Tense / Premature:** Describing intended changes or future work as already being complete. |
| | **Subjective Proof:** Offering "I wrote the code" or "the logic is correct" as the sole evidence of functionality. |

### 4. System Configuration and Environment
Configuration is handled via environment variables read at process start. This allows for seamless tuning without modifying the hook source.

| Variable Name | Default Value | Functional Purpose |
| :--- | :--- | :--- |
| `OLLAMA_URL` | `http://localhost:11434/api/generate` | The local endpoint for the verifier model. |
| `OLLAMA_VERIFIER_MODEL` | `llama3.2:3b` | The model used for judgment. (See Section 7 for trade-offs). |
| `OLLAMA_VERIFIER_TIMEOUT_S` | `20` | Timeout for the Ollama call. Must be lower than the **35,000ms** Claude Code hook timeout. |
| `OLLAMA_VERIFIER_KEEP_ALIVE` | `24h` | Keeps the model resident in VRAM to eliminate cold-start latency. |
| `VALIDATION_GATE_VERDICT_DIR` | `~/.claude/validation-gate/verdicts` | Storage for detailed per-invocation JSON verdict files. |
| `VALIDATION_GATE_LOG` | `~/.claude/validation-gate/gate.log` | Central append-only activity log. |
| `VALIDATION_GATE_NOTIFY` | *(unset)* | Path to an executable run on **FAIL**. Invoked as: `<script> error <subject> <body>`. |

#### Zero-Dependency Architecture
The gate is designed for maximum environment reliability and the prevention of dependency drift. It relies exclusively on the Python standard library, categorized as follows:
*   **Networking:** `urllib.request`, `urllib.error` (Ollama communication).
*   **OS & Environment:** `os`, `pathlib`, `sys`, `datetime`, `time` (Config, IO, and performance).
*   **Parsing & Processing:** `re` (Pre-filtering and response cleaning), `json` (Payload handling).
*   **Execution:** `subprocess` (Notification script execution).

### 5. Operational Audit and Verdict Logging
System monitoring is facilitated through two primary audit mechanisms:

*   **Verdict Directory:** Stores detailed state for every verifier call.
    *   **Naming Convention:** `<UTC-timestamp>_<session-id-prefix>.json`.
    *   **Example:** `20260724T191500Z_a1b2c3d4.json`.
    *   **Retention:** The gate does not automatically prune files. Administrators should implement a rotation policy (e.g., `find $DIR -mtime +30 -delete`) to prevent disk exhaustion.
*   **Append-only Log:** Records one line per invocation, noting the model used, session ID, and verdict.
*   **FAIL Notification:** If `VALIDATION_GATE_NOTIFY` is set, the gate triggers the external script with the format `<script> error <subject> <body>`. This call has a 5-second timeout and is "best-effort" to ensure notifications never block the main loop.

### 6. Fail-Open Behavior and Safety Mechanisms
To prevent "wedging" a coding session, the gate follows a strict **Fail-Open** philosophy. A turn is only blocked on an explicit **FAIL** verdict.

**Reference Checklist of Pass-Through Scenarios:**
*   **[System Errors]**
    *   [ ] Ollama service unreachable (Connection Refused/DNS).
    *   [ ] Verifier request exceeds `OLLAMA_VERIFIER_TIMEOUT_S`.
    *   [ ] Model returns unparseable or malformed JSON.
*   **[Logic Pass-throughs]**
    *   [ ] Assistant message contains no completion language keywords.
    *   [ ] Stop payload from Claude Code is empty or missing `last_assistant_message`.
    *   [ ] **Loop Protection:** Payload contains `stop_hook_active: true`, indicating the turn was already triggered by a prior block.

#### Security and Privacy
*   **Local Processing:** By default, all transcript data remains on the local machine. **Warning:** Redirecting `OLLAMA_URL` to a remote endpoint will cause session transcript excerpts to leave the local network.
*   **Data Sensitivity:** Verdict files contain 2000-character excerpts of the conversation. These directories should be secured with the same permissions as your primary session transcripts.

### 7. Operational Tuning and Maintenance
Infrastructure engineers can balance verification rigor against latency using the following trade-off analysis:

1.  **Model Selection (Accuracy vs. Latency):**
    *   **3B Models (Default):** Extremely fast but err toward "false blocks" due to limited reasoning.
    *   **8B+ Models:** Significantly more balanced and accurate at identifying subtle evidence, but require higher latency budgets.
2.  **Latency Optimization:** Ensure `OLLAMA_VERIFIER_KEEP_ALIVE` is active to maintain a warm cache.
3.  **Timeout Alignment:** Maintain a buffer between `OLLAMA_VERIFIER_TIMEOUT_S` (default 20s) and the `settings.json` hook timeout (35,000ms) to allow for IO overhead and model loading.

#### Operational Checklist
*   [ ] **Service Check:** Verify Ollama is running and the model is pulled (`ollama pull <model>`).
*   [ ] **Configuration:** Use the provided `install.sh` to generate the **absolute path** for the `settings.json` "Stop" hook entry.
*   [ ] **Persistence:** Ensure the verdict/log directory is writable by the user running Claude Code.
*   [ ] **Validation:** Run `./tests/test_gate.sh` to smoke test both pass-through and blocking behavior.