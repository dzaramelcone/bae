---
status: complete
phase: 30-agent-core-extraction
source: [30-01-SUMMARY.md, 30-02-SUMMARY.md]
started: 2026-02-15T14:45:00Z
updated: 2026-02-15T14:55:00Z
---

## Current Test

[testing complete]

## Tests

### 1. _cli_send against real Claude CLI
expected: _cli_send sends prompt to real Claude CLI, gets response. First call uses --session-id, second uses --resume on same session.
result: pass
method: real CLI call with haiku, verified PING_OK and RESUME_OK responses

### 2. agent_loop real multi-turn with code execution
expected: agent_loop sends "Calculate 7*13" to real Claude, LM returns <run> block, agent executes it, feeds output back, LM confirms 91.
result: pass
method: real CLI + real async_exec, verified 2 round-trips and correct answer

### 3. AgenticBackend.fill() end-to-end
expected: AgenticBackend.fill(CityFact, {}, 'CityFact') produces a CityFact with real city/country/population data.
result: issue
reported: "fill() returned city='CityFact', country='Unknown', population_millions=0.0 — prompt didn't include target schema so LM had no idea what fields to research"
severity: blocker

### 4. AgenticBackend.fill() after fix
expected: After including target schema in Phase 1 prompt, fill() returns real data.
result: pass
method: real CLI call, returned CityFact(city='Tokyo', country='Japan', population_millions=37.4)

### 5. Existing tests still pass after fix
expected: All 84 agent + AI tests pass with no regression.
result: pass
method: uv run pytest tests/test_agent.py tests/repl/test_ai.py — 84 passed

## Summary

total: 5
passed: 4
issues: 1
pending: 0
skipped: 0

## Gaps

- truth: "AgenticBackend.fill() produces correct typed output from real LM"
  status: fixed
  reason: "Phase 1 prompt was just the instruction string ('CityFact') with no schema — LM had no context about what fields to fill"
  severity: blocker
  test: 3
  root_cause: "AgenticBackend.fill() called _build_fill_prompt which excludes output schema (by design for ClaudeCLIBackend where --json-schema handles it), but agent_loop's Phase 1 needs the schema in-prompt since it's free-form research"
  fix: "Hoisted _build_plain_model + transform_schema before Phase 1, appended JSON schema to research prompt"
  artifacts:
    - path: "bae/lm.py"
      issue: "Missing target schema in agentic research prompt"
  missing: []
