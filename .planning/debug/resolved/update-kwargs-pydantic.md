---
status: resolved
trigger: "Diagnose root cause for this UAT gap: **Gap:** `update(\"task-id\", status=\"in_progress\")` fails with pydantic validation error"
created: 2026-02-16T00:00:00Z
updated: 2026-02-16T00:00:00Z
---

## Current Focus

hypothesis: _build_validator() creates pydantic model with 'kwargs' field from **kwargs param
test: Trace what pydantic model fields are created from update(task_id: str, **kwargs) signature
expecting: Model has task_id field + kwargs field (instead of accepting any extra fields)
next_action: Verify hypothesis by examining model creation logic

## Symptoms

expected: update("task-id", status="in_progress") should work
actual: Pydantic validation error "Field required"
errors:
- update("id", "in_progress") → "Cannot update field 'kwargs'" (positional goes to kwargs)
- update("id", status="in_progress") → pydantic "Field required" error
- Only update(task_id="id", status="in_progress") works
reproduction: Call update() from tasks resourcespace with mixed positional/keyword args
started: Phase 32.2 pydantic validation wrapper implementation

## Eliminated

## Evidence

- timestamp: 2026-02-16T00:00:00Z
  checked: TaskResourcespace.update() signature
  found: def update(self, task_id: str, **kwargs) -> str
  implication: Uses **kwargs to accept arbitrary update fields

- timestamp: 2026-02-16T00:00:00Z
  checked: ResourceRegistry._make_tool_wrapper()
  found: Wraps tools with _validate_tool_params, handles positional args specially
  implication: Wrapper tries to convert args to kwargs and validate

- timestamp: 2026-02-16T00:00:01Z
  checked: _build_validator() in tools.py lines 27-55
  found: Iterates sig.parameters, creates pydantic model field for EACH parameter
  implication: **kwargs becomes a field named 'kwargs' in the pydantic model

- timestamp: 2026-02-16T00:00:02Z
  checked: _validate_tool_params() in tools.py lines 58-76
  found: Builds params dict, then calls validator(**params) which expects exact fields
  implication: When you pass status="in_progress", pydantic looks for a 'status' field but model only has 'task_id' and 'kwargs'

- timestamp: 2026-02-16T00:00:03Z
  checked: inspect.signature behavior with **kwargs
  found: **kwargs parameter has kind=VAR_KEYWORD, but _build_validator doesn't check param.kind
  implication: _build_validator treats VAR_KEYWORD like a regular parameter, creates a field named 'kwargs'

## Resolution

root_cause: _build_validator() in tools.py doesn't skip VAR_KEYWORD parameters when building pydantic model. It creates a field named 'kwargs' instead of allowing arbitrary extra fields. When calling update("id", status="in_progress"), pydantic expects fields ['task_id', 'kwargs'] but receives ['task_id', 'status'], causing validation error.

The VAR_KEYWORD parameter (inspect.Parameter.kind == inspect.Parameter.VAR_KEYWORD) should be skipped when building the pydantic model, and the model should use extra='allow' to accept arbitrary additional fields.

fix: Two options:
1. Fix _build_validator() to skip VAR_KEYWORD params and use extra='allow' (general solution)
2. Change update() signature to explicit keyword params: update(task_id: str, status: str = None, priority: str = None, ...) (specific to this method)

Option 1 is better because:
- Handles any future **kwargs methods
- Matches the intent of **kwargs (accept arbitrary fields)
- Less brittle than maintaining explicit param list
verification:
files_changed: []
