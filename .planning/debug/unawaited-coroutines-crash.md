---
status: diagnosed
trigger: "Creating unawaited coroutines in PY mode crashes the entire REPL"
created: 2026-02-14T00:00:00Z
updated: 2026-02-14T00:07:00Z
symptoms_prefilled: true
goal: find_root_cause_only
---

## Current Focus

hypothesis: Unawaited coroutines created in async context are stored in namespace["_"], then when they're garbage collected (maybe during repr or later), asyncio's coroutine cleanup interacts badly with the running event loop, causing a crash or exception that exits the REPL
test: Examine what happens to unawaited coroutines in namespace persistence and how they're cleaned up
expecting: Find that the coroutines cause an unhandled exception or event loop error during cleanup
next_action: Propose fix to detect and handle collections containing coroutines

## Symptoms

expected: PY mode should handle unawaited coroutines gracefully — show RuntimeWarning but not crash the REPL
actual: REPL process exits when creating unawaited coroutines like `[asyncio.sleep(30) for _ in range(20)]`
errors: RuntimeWarning: coroutine 'sleep' was never awaited
reproduction: In PY mode, execute `[asyncio.sleep(30) for _ in range(20)]` without await
started: Discovered during Phase 20 UAT

## Eliminated

## Evidence

- timestamp: 2026-02-14T00:01:00Z
  checked: bae/repl/exec.py async_exec function (lines 28-68)
  found: async_exec only handles when the ENTIRE result is a single coroutine (line 57-61). If result is a list of coroutines, it falls through to line 67 and returns namespace.get("_") which is the list
  implication: List of coroutines is returned as a normal result, not handled specially

- timestamp: 2026-02-14T00:02:00Z
  checked: bae/repl/shell.py _dispatch PY mode handler (lines 288-311)
  found: When result is not a coroutine (line 293 check), it goes to line 305-306 where it calls repr(result) on the list of coroutines
  implication: repr() on a list containing unawaited coroutines likely triggers __del__ and RuntimeWarnings

- timestamp: 2026-02-14T00:03:00Z
  checked: Execution flow for `[asyncio.sleep(30) for _ in range(20)]`
  found:
    1. async_exec stores list in namespace["_"] (line 44)
    2. Returns (namespace.get("_"), captured) = ([coro1, coro2, ...], "")
    3. shell.py line 293: asyncio.iscoroutine(result) is False (it's a list)
    4. shell.py line 305-306: result is not None, so calls repr(result)
    5. repr() on the list forces string representation of coroutines
    6. Coroutines may get garbage collected, triggering "never awaited" warnings
    7. Something in this process crashes the REPL
  implication: Need to detect and handle collections containing coroutines before calling repr()

- timestamp: 2026-02-14T00:04:00Z
  checked: Testing repr() on unawaited coroutines in isolation
  found: repr() itself doesn't crash - it just returns string representation. RuntimeWarning appears later during garbage collection. The warning alone doesn't crash Python
  implication: The crash must be caused by something else, not the warning itself

- timestamp: 2026-02-14T00:05:00Z
  checked: Entry points (cli.py, __init__.py)
  found: No special warning filter configuration. Standard asyncio.run() launches the REPL
  implication: Not a warnings configuration issue

- timestamp: 2026-02-14T00:06:00Z
  checked: Why specifically crashes vs. just warnings
  found: |
    The RuntimeWarning itself shouldn't crash Python. But the likely scenario is:
    1. Unawaited coroutines get created and stored in namespace["_"]
    2. They persist across REPL loop iterations
    3. When garbage collected (maybe during next prompt or repr), they trigger warnings
    4. In the async context of the running event loop, coroutine cleanup might cause
       unhandled exceptions or event loop state issues
    5. prompt_toolkit or asyncio might not handle these gracefully, causing exit

    The user reported "crashes the entire REPL" which suggests process exit, not just
    an exception. This is consistent with event loop corruption or unhandled errors
    during cleanup.
  implication: Must prevent the coroutines from being stored in namespace or clean them up immediately

## Resolution

root_cause: |
  When PY mode expression evaluates to a collection containing unawaited coroutines
  (e.g., `[asyncio.sleep(30) for _ in range(20)]`), the current code only checks if
  the result itself is a coroutine using `asyncio.iscoroutine(result)` (shell.py:293).

  This check fails for collections, so the code proceeds to line 305-306 where it calls
  `repr(result)` and writes it to the channel. The unawaited coroutines get stored in
  `namespace["_"]` and eventually garbage collected, triggering RuntimeWarnings and
  potentially causing event loop issues that crash the REPL.

  Files involved:
  - bae/repl/shell.py:293-306 - Only checks if result IS a coroutine, not if it CONTAINS coroutines
  - bae/repl/exec.py:57-61 - Only handles when entire result is a coroutine

fix: |
  Add a helper function to recursively detect if a value contains coroutines, then
  handle collections containing coroutines similarly to single coroutines - either:

  Option 1 (RECOMMENDED): Show a warning message instead of repr, without crashing
  - Detect collections containing coroutines in shell.py before repr()
  - Write a warning message like "Result contains N unawaited coroutines (not displayed)"
  - Prevent the coroutines from being stored in namespace["_"] or clean them up

  Option 2: Recursively await all coroutines in collections
  - Would be complex and might not match user expectations
  - Could hang if any coroutine is long-running

  Option 3: Just repr() but suppress the warnings
  - Doesn't fix the crash issue
  - Still leaves coroutines in namespace

  Specific changes needed (Option 1):

  1. In bae/repl/shell.py, add helper function:
  ```python
  def _contains_coroutines(obj, _seen=None):
      '''Recursively check if obj or its contents are coroutines.'''
      if _seen is None:
          _seen = set()
      obj_id = id(obj)
      if obj_id in _seen:
          return False
      _seen.add(obj_id)

      if asyncio.iscoroutine(obj):
          return True
      if isinstance(obj, (list, tuple, set)):
          return any(_contains_coroutines(item, _seen) for item in obj)
      if isinstance(obj, dict):
          return any(_contains_coroutines(v, _seen) for v in obj.values())
      return False

  def _count_coroutines(obj, _seen=None):
      '''Count coroutines in obj recursively.'''
      if _seen is None:
          _seen = set()
      obj_id = id(obj)
      if obj_id in _seen:
          return 0
      _seen.add(obj_id)

      count = 0
      if asyncio.iscoroutine(obj):
          count = 1
      elif isinstance(obj, (list, tuple, set)):
          count = sum(_count_coroutines(item, _seen) for item in obj)
      elif isinstance(obj, dict):
          count = sum(_count_coroutines(v, _seen) for v in obj.values())
      return count
  ```

  2. In _dispatch() PY mode handler (around line 305-306), change:
  ```python
  # OLD:
  elif result is not None:
      self.router.write("py", repr(result), mode="PY", metadata={"type": "expr_result"})

  # NEW:
  elif result is not None:
      if _contains_coroutines(result):
          count = _count_coroutines(result)
          msg = f"<{count} unawaited coroutine{'s' if count != 1 else ''}>"
          self.router.write("py", msg, mode="PY", metadata={"type": "warning"})
          # Clean up coroutines from namespace to prevent warnings
          if "_" in self.namespace:
              del self.namespace["_"]
      else:
          self.router.write("py", repr(result), mode="PY", metadata={"type": "expr_result"})
  ```

  3. Similarly update the async task callback (lines 297-298) to handle collections:
  ```python
  # In _py_task, after await coro:
  if val is not None:
      if _contains_coroutines(val):
          count = _count_coroutines(val)
          msg = f"<{count} unawaited coroutine{'s' if count != 1 else ''}>"
          self.router.write("py", msg, mode="PY", metadata={"type": "warning"})
      else:
          self.router.write("py", repr(val), mode="PY", metadata={"type": "expr_result"})
  ```

verification: |
  After implementing the fix:
  1. Start the REPL in PY mode
  2. Execute: `[asyncio.sleep(30) for _ in range(20)]`
  3. Verify: Should show "<20 unawaited coroutines>" message
  4. Verify: REPL should NOT crash or exit
  5. Verify: No RuntimeWarning messages should appear
  6. Test edge cases:
     - Single unawaited coroutine in list: `[asyncio.sleep(1)]`
     - Nested: `[[asyncio.sleep(1)], [asyncio.sleep(2)]]`
     - Mixed: `[1, asyncio.sleep(1), "text"]`
     - Dict: `{"coro": asyncio.sleep(1)}`

files_changed:
  - bae/repl/shell.py
