---
phase: 02
plan: 03
subsystem: lm-backend
tags: [dspy, predict, retry, error-handling, tdd]
dependency-graph:
  requires: [01-01, 02-01]
  provides: [dspy-backend]
  affects: [02-04, 03-*]
tech-stack:
  added: []
  patterns: [self-correction-retry, two-step-decide]
key-files:
  created:
    - bae/dspy_backend.py
    - tests/test_dspy_backend.py
  modified: []
decisions:
  - id: dspy-predict-pattern
    choice: Use dspy.Predict with node_to_signature
    rationale: Consistent with DSPy optimization patterns
  - id: self-correction-hint
    choice: Pass parse error as additional input on retry
    rationale: Gives LLM context about failure, improves retry success
  - id: two-step-decide
    choice: Separate choice prediction from instance creation
    rationale: Simpler signatures, better type safety
metrics:
  duration: 4 min
  completed: 2025-02-04
---

# Phase 2 Plan 3: DSPyBackend Summary

**One-liner:** DSPyBackend using dspy.Predict with generated Signatures, self-correction retry, and two-step union handling

## What Was Built

### DSPyBackend Class (bae/dspy_backend.py)

Core LM backend implementing the LM protocol with DSPy:

1. **make(node, target, **deps)** - Produces target Node instance
   - Gets signature via `node_to_signature(target)`
   - Creates `dspy.Predict(signature)`
   - Extracts Context-annotated fields from node as inputs
   - Passes Dep values from kwargs as additional inputs
   - Parses JSON output to Pydantic model
   - On parse failure: retries once with error hint in inputs
   - Raises `BaeParseError` after retry exhausted

2. **decide(node)** - Two-step pattern for union return types
   - Inspects node's `__call__` return type hint
   - Single type: calls `make()` directly (no choice step)
   - Union types: first predicts choice, then calls `make()`
   - Returns None if LLM chooses None (terminal)

3. **API Error Handling**
   - Catches litellm exceptions (Timeout, RateLimitError, APIError, etc.)
   - Waits 1 second before retry
   - Retries once, raises `BaeLMError` on persistent failure
   - Chains original exception as `__cause__`

### Test Coverage (tests/test_dspy_backend.py)

15 tests covering:
- Signature generation integration
- Context field extraction and passing
- Parse failure retry with error hints
- BaeParseError after exhausted retries
- Two-step decide for unions
- Choice bypass for single types
- API timeout/rate limit retry
- BaeLMError after API retry exhausted
- Retry timing verification
- Dep field passing

## Key Implementation Details

```python
# Self-correction pattern - retry with error hint
for attempt in range(self.max_retries + 1):
    error_hint = str(last_error) if last_error else None
    try:
        result = self._call_with_retry(predictor, inputs, error_hint)
        return self._parse_output(result.output, target)
    except ValueError as e:
        last_error = e
        if attempt < self.max_retries:
            continue
        raise BaeParseError(str(e), cause=e) from e
```

```python
# Two-step decide - choice then make
if len(types_list) == 1 and not is_terminal:
    return self.make(node, types_list[0])  # Skip choice

choice = self._predict_choice(node, types_list, is_terminal)
if choice == "None":
    return None
return self.make(node, target)
```

## Deviations from Plan

None - plan executed exactly as written.

## Verification Results

```
pytest tests/test_dspy_backend.py -v
15 passed

pytest tests/ -v
75 passed, 5 skipped (integration tests skipped without API key)
```

## Next Phase Readiness

DSPyBackend is ready for:
- Integration with Graph.run() for automatic LM selection
- DSPy optimization passes (BootstrapFewShot, etc.)
- Real LLM testing once API keys configured

Dependencies satisfied:
- Uses `node_to_signature` from 01-01
- Uses exceptions from 02-01
