---
status: diagnosed
trigger: "Investigate why phase 32.2 tool summary, validation, and response suppression features don't work in the live REPL"
created: 2026-02-16T22:00:00Z
updated: 2026-02-16T22:30:00Z
---

## Current Focus

hypothesis: confirmed -- see Resolution
test: code path trace complete
expecting: n/a
next_action: fix decision needed from Dzara

## Symptoms

expected: Tool calls display as diamond-bullet summaries, pydantic validation fires on bad params, resource context prefix appears
actual: Tool results show as full execution blocks in ai:1 panels; read(325035) gives raw TypeError; no diamond-bullet or [source] prefix anywhere
errors: TypeError from _validate_module_path instead of pydantic validation error
reproduction: Navigate to source(), then ask AI anything that triggers read/glob/grep. AI emits <run>read("bae")</run> blocks, not <Read:bae> XML tags.
started: Since 32.2 implementation -- features were built on wrong code path

## Eliminated

(none needed -- root cause identified on first hypothesis)

## Evidence

- timestamp: 2026-02-16T22:05:00Z
  checked: How AI calls tools in eval loop (ai.py lines 131-216)
  found: Two tool-call paths exist. Path A (lines 135-158) scans for XML tags like <Read:bae> via run_tool_calls() and renders via "tool_translated" metadata type. Path B (lines 161-199) executes <run> blocks containing arbitrary Python via async_exec() and renders via "ai_exec" / "ai_exec_result" metadata types.
  implication: All 32.2 features (summaries, validation, resource prefix) were built on Path A only

- timestamp: 2026-02-16T22:08:00Z
  checked: What the AI subprocess actually emits
  found: The AI (claude CLI subprocess) receives a namespace with read/glob/grep/etc as direct Python callables (injected by _put_tools in spaces/view.py lines 205-215). The AI's system prompt tells it to use <run> blocks with Python code. So the AI writes <run>read("bae")</run>, NOT <Read:bae> XML tags.
  implication: Path B fires every time. Path A (with all 32.2 features) never fires.

- timestamp: 2026-02-16T22:10:00Z
  checked: Where namespace callables come from (SourceResourcespace.tools(), spaces/view.py _put_tools)
  found: SourceResourcespace.tools() returns {"read": self.read, "write": self.write, ...} -- these are raw bound methods. _put_tools() injects them directly into the namespace dict. No wrapper, no validation, no summarization.
  implication: When AI calls read("bae") in a <run> block, it calls SourceResourcespace.read("bae") directly. ToolRouter.dispatch() is never invoked. Pydantic validation in _validate_tool_params never fires.

- timestamp: 2026-02-16T22:12:00Z
  checked: How <run> block results render (views.py UserView)
  found: ai_exec writes buffer as pending code (line 145-147). ai_exec_result triggers _render_grouped_panel (line 149-153) which shows a framed Rich Panel with syntax-highlighted code + output. There is NO tool_translated handling in this path -- the output is the full string, not a summary.
  implication: Even if we added summaries to the callables, the UserView render path would still show full panels, not one-liner summaries.

- timestamp: 2026-02-16T22:15:00Z
  checked: Where run_tool_calls XML path gets invoked
  found: run_tool_calls() parses prose (non-<run>, non-fence text) for XML tags like <Read:bae>, <Write:path>content</Write>, <Glob:pattern>, and OSC8 hyperlinks. It dispatches through ToolRouter when available. But the AI never produces these tags because the system prompt instructs it to use Python callables in <run> blocks.
  implication: run_tool_calls is dead code in practice -- the AI always takes the <run> block path

- timestamp: 2026-02-16T22:18:00Z
  checked: ToolRouter.dispatch() validation pipeline (tools.py)
  found: dispatch() calls _validate_tool_params() which builds a pydantic model from the method signature and validates inputs. On validation error, returns a formatted error string with usage hint. This only fires when called through dispatch(), never when the AI calls the bound method directly.
  implication: read(325035) goes straight to SourceResourcespace.read(325035) which calls _validate_module_path(325035) which raises raw TypeError because it expects a string

- timestamp: 2026-02-16T22:20:00Z
  checked: _tool_summary formatting (ai.py lines 361-394)
  found: _tool_summary() formats a tag string like "<Read:bae>" into "diamond-bullet read(bae) -> str (42 lines)" with optional [resource] prefix. Only called at line 139 inside the run_tool_calls results loop. Never called for <run> block execution results.
  implication: Summary formatting exists but is unreachable from the actual code path

## Resolution

root_cause: |
  Architecture mismatch between how the AI calls tools and where 32.2 features were implemented.

  THE ACTUAL PATH (fires every time):
    1. AI subprocess receives namespace with read/glob/grep as Python callables
    2. AI emits <run>read("bae")</run> in response text
    3. ai.py extract_executable() finds the <run> block
    4. async_exec() evaluates read("bae") in namespace -- calls SourceResourcespace.read() directly
    5. Result written to channel as type="ai_exec" + type="ai_exec_result"
    6. UserView renders as framed Rich Panel with full code + output

  THE IMPLEMENTED PATH (never fires):
    1. AI would emit bare <Read:bae> XML tag in prose (outside <run> blocks)
    2. run_tool_calls() would parse the XML tag
    3. ToolRouter.dispatch() would validate params via pydantic
    4. _tool_summary() would format as diamond-bullet one-liner
    5. Result written to channel as type="tool_translated"
    6. UserView renders as dim/red ANSI one-liner

  The features are correct in isolation -- they're just on a path the AI never takes.

fix: ""
verification: ""
files_changed: []

## Fix Direction Analysis

Three possible fix strategies, from least to most invasive:

### Strategy A: Wrap namespace callables (smallest change)

Replace raw bound methods with wrapper functions that go through ToolRouter.dispatch():

In `_put_tools()` or `tools()`, instead of injecting `self.read` directly, inject a wrapper that:
1. Routes through ToolRouter.dispatch() for validation
2. Writes tool_translated metadata to channel router (needs access to channel router)
3. Returns result

Problem: The wrapper needs access to both the ToolRouter and ChannelRouter, which the resource doesn't have. Also, the AI's <run> block execution still writes ai_exec/ai_exec_result -- double-rendering.

### Strategy B: Detect tool calls in <run> block results (medium change)

In the eval loop (ai.py lines 161-199), after async_exec(), detect if the executed code was a known tool call (e.g., matches `read(...)`, `glob(...)`, etc.) and render it as a summary instead of a full panel.

Steps:
1. After exec, check if the code is a simple tool call (regex: `^(read|write|edit|glob|grep)\(.*\)$`)
2. If yes, format with _tool_summary() and write as tool_translated instead of ai_exec
3. Route validation through ToolRouter.dispatch() instead of direct call

Problem: Would need to intercept the call BEFORE exec to add validation. Can't validate after the fact.

### Strategy C: Replace namespace callables with router-dispatched wrappers (recommended)

Modify `_put_tools()` in ResourceRegistry to wrap each tool callable:

```python
def _put_tools(self) -> None:
    if self._namespace is None:
        return
    for name in _TOOL_NAMES:
        self._namespace.pop(name, None)
    current = self.current
    if current is not None:
        for tool_name, method in current.tools().items():
            self._namespace[tool_name] = self._make_tool_wrapper(tool_name, method)
    elif self._home_tools:
        self._namespace.update(self._home_tools)
```

The wrapper would:
1. Run pydantic validation via _validate_tool_params
2. Call the underlying method
3. Return the result (for async_exec to capture)

For **summaries**, the rendering side also needs change: the eval loop in ai.py needs to detect tool calls in <run> blocks and write tool_translated metadata instead of ai_exec metadata.

**Key insight:** Validation and summarization are separate concerns:
- Validation = wrap the callable (fires before execution)
- Summarization = change how the result is rendered (fires after execution)

Both need fixing, but in different places.
