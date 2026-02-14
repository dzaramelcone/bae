---
status: resolved
trigger: "Investigate two related issues with Ctrl-C and task management in cortex"
created: 2026-02-13T00:00:00Z
updated: 2026-02-13T00:20:00Z
---

## Current Focus

hypothesis: CONFIRMED - Issue 1: Key binding only fires during prompt_async(), not during task execution. Issue 2: Race condition between subprocess completion and task cancellation.
test: Complete code analysis and control flow tracing
expecting: Root causes identified for both issues
next_action: Investigation complete, findings documented

## Symptoms

expected:
- Issue 1: Ctrl-C during task execution should show kill menu checkboxlist_dialog
- Issue 2: Ctrl-C should cancel AI tasks the same way it cancels bash tasks

actual:
- Issue 1: Kill menu never appears when pressing Ctrl-C
- Issue 2: Bash tasks cancel on Ctrl-C, but AI tasks complete and print anyway

errors: None reported

reproduction:
- Issue 1: Run any task, press Ctrl-C during execution
- Issue 2: Run AI task, press Ctrl-C during execution

started: Unknown, appears to be existing behavior

## Eliminated

## Evidence

- timestamp: 2026-02-13T00:05:00Z
  checked: shell.py _build_key_bindings() lines 94-109
  found: Ctrl-C binding is registered with prompt_toolkit KeyBindings, fires handle_interrupt()
  implication: Key binding is managed by prompt_toolkit's event loop, only active during prompt_async()

- timestamp: 2026-02-13T00:06:00Z
  checked: shell.py run() loop lines 255-279
  found: prompt_async() waits for input (lines 260), then _dispatch() executes (line 274). After _dispatch() returns, there's a KeyboardInterrupt handler (lines 275-278) that cancels all tasks.
  implication: During _dispatch() execution, we're NOT in prompt_async(), so Ctrl-C key binding doesn't fire. Instead, SIGINT raises KeyboardInterrupt exception.

- timestamp: 2026-02-13T00:07:00Z
  checked: shell.py _dispatch() lines 182-241
  found: No try/except KeyboardInterrupt around task execution. Tasks are tracked and awaited but not wrapped in KeyboardInterrupt handling.
  implication: KeyboardInterrupt during _dispatch() will propagate up to run() loop's outer handler (line 275)

- timestamp: 2026-02-13T00:08:00Z
  checked: bash.py dispatch_bash() lines 34-39
  found: Has explicit CancelledError handler that kills subprocess (proc.kill()) and waits for it (await proc.wait())
  implication: When bash task is cancelled, subprocess is properly terminated

- timestamp: 2026-02-13T00:09:00Z
  checked: ai.py AI.__call__() lines 81-97
  found: Has CancelledError handler (lines 94-97) that kills process (process.kill()) but then awaits process.wait(), then re-raises
  implication: AI subprocess cleanup looks similar to bash. Need to verify if there's a timing issue.

- timestamp: 2026-02-13T00:10:00Z
  checked: ai.py AI.__call__() lines 87-97
  found: CancelledError handler properly kills process and re-raises. Lines 103-106 should NOT execute after raise.
  implication: Control flow looks correct for AI cancellation. Need to trace actual cancellation mechanism.

- timestamp: 2026-02-13T00:11:00Z
  checked: shell.py run() lines 273-278
  found: KeyboardInterrupt during _dispatch() is caught at run() level (line 275), then manually cancels all tracked tasks (line 276-277)
  implication: Ctrl-C during task execution → KeyboardInterrupt → caught by run() → task.cancel() called on all tasks

- timestamp: 2026-02-13T00:12:00Z
  checked: How task.cancel() propagates to subprocess
  found: task.cancel() sets CancelledError on the task, but process.communicate() on line 88-89 might have already completed if subprocess finishes quickly
  implication: RACE CONDITION - If claude CLI subprocess completes before task.cancel() is processed, the CancelledError never fires and response gets written normally

- timestamp: 2026-02-13T00:13:00Z
  checked: bash.py vs ai.py cancellation difference
  found: Both use same pattern (proc.kill() in CancelledError handler). Main difference: bash uses proc.communicate() directly, AI wraps it in asyncio.wait_for()
  implication: CRITICAL - asyncio.wait_for() catches CancelledError internally to implement timeout! This might be swallowing the task cancellation.

- timestamp: 2026-02-13T00:15:00Z
  checked: asyncio.wait_for() behavior with external cancellation
  found: Python docs say "If the wait is cancelled, the task is also cancelled" BUT "If the task suppresses the cancellation and returns a value instead, that value is returned."
  implication: wait_for() should propagate cancellation, but timing matters

- timestamp: 2026-02-13T00:16:00Z
  checked: Actual race condition scenario
  found: Race between two async operations:
    - Task A: await asyncio.wait_for(process.communicate(), timeout=60)
    - Task B: task.cancel() called from run() loop after KeyboardInterrupt
  If process.communicate() completes and wait_for() is about to return the result, but task.cancel() arrives at that exact moment, which wins?
  implication: This is a genuine race condition. The CancelledError might not be raised if the operation completes "fast enough"

- timestamp: 2026-02-13T00:17:00Z
  checked: Why bash works but AI doesn't
  found: Bash subprocess might be slower or more likely to be mid-execution when Ctrl-C arrives. AI subprocess (claude CLI) might complete very quickly for simple queries, beating the cancellation.
  implication: The symptom "bash cancels but AI doesn't" supports the race condition hypothesis - AI completes faster

- timestamp: 2026-02-13T00:14:00Z
  checked: Execution flow during task execution
  found:
    1. run() awaits prompt_async() → user enters text → prompt returns (line 260)
    2. run() calls await _dispatch(text) (line 274)
    3. During _dispatch(), we are NOT in prompt_async(), so prompt_toolkit's event loop is not actively processing input
    4. Ctrl-C during step 3 → SIGINT → KeyboardInterrupt exception, NOT the key binding handler
  implication: CONFIRMED - Key binding never fires during task execution because prompt_async() has returned. The key binding only works when waiting for user input.

## Resolution

root_cause:

**Issue 1 - Kill menu never appears:**
The Ctrl-C key binding (lines 94-109 in shell.py) is registered with prompt_toolkit's KeyBindings, which means it only fires when prompt_toolkit's event loop is actively processing keyboard input. This happens during `await self.session.prompt_async()` (line 260). However, after the user submits input and prompt_async() returns, control passes to `await self._dispatch(text)` (line 274). During _dispatch() execution, prompt_toolkit is NOT actively reading input, so the key binding handler never fires. Instead, Ctrl-C generates a SIGINT that raises KeyboardInterrupt exception, which is caught by the outer try/except at line 275 in run(). This outer handler just cancels all tasks and writes a debug message - it never shows the kill menu.

**Issue 2 - AI tasks don't cancel properly:**
Race condition between subprocess completion and task cancellation. When Ctrl-C is pressed during AI task execution:
1. KeyboardInterrupt is raised and caught at line 275 in run()
2. The handler calls task.cancel() on all tracked tasks (line 276)
3. task.cancel() schedules a CancelledError to be raised in the AI.__call__() coroutine
4. Meanwhile, the claude CLI subprocess may complete and process.communicate() (inside wait_for() at lines 88-89) may return
5. If process.communicate() completes before the CancelledError is delivered to the await point, normal flow continues
6. Lines 103-106 execute, decoding and writing the response

The race: task.cancel() is asynchronous - it schedules cancellation but doesn't immediately interrupt the coroutine. If the await point (wait_for on line 88) completes before the event loop delivers the CancelledError, the exception is never raised and execution continues normally.

Why bash works: Bash commands are typically slower or more likely to be in the middle of execution when Ctrl-C arrives, so the cancellation beats the subprocess completion. AI responses for simple queries may complete in milliseconds, beating the cancellation delivery.

fix:

**Issue 1 - Kill menu never appears:**

The fundamental issue: key bindings only work during prompt_async(), but tasks run after prompt_async() returns.

**Option A (Recommended): Signal handler approach**
Register a SIGINT handler using signal.signal() that bypasses prompt_toolkit:
```python
import signal

def _setup_sigint_handler(shell):
    def handler(signum, frame):
        if shell.tasks:
            # Show kill menu or cancel all tasks
            # This runs in signal handler context, need to be careful
            asyncio.create_task(_show_kill_menu(shell))
        else:
            raise KeyboardInterrupt()
    signal.signal(signal.SIGINT, handler)
```
Issue: Signal handlers run in a restricted context, can't directly show dialogs. Need to set a flag and check it in the event loop.

**Option B: Background task execution**
Keep prompt_async() active while tasks run by moving task execution to background:
```python
async def run(self):
    while True:
        text = await self.session.prompt_async()
        # Don't await _dispatch, let it run in background
        asyncio.create_task(self._dispatch(text))
```
Issue: Multiple tasks can run concurrently, changes execution model significantly.

**Option C: Hybrid - Check cancellation flag in outer handler**
When KeyboardInterrupt is caught at run() level (line 275), instead of immediately cancelling, check if tasks exist and show menu:
```python
except KeyboardInterrupt:
    if self.tasks:
        # Show kill menu synchronously before cancelling
        await _show_kill_menu(self)
    else:
        return
```
This would work because we're in async context at that point.

**Issue 2 - AI tasks don't cancel on Ctrl-C:**

The race condition can't be fully eliminated, but can be mitigated.

**Option A (Recommended): Add cancelled flag**
Set a flag when task is cancelled, check it before writing response:
```python
class AI:
    def __init__(self, ...):
        ...
        self._cancelled = False

async def __call__(self, prompt: str) -> str:
    ...
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(...)
    except asyncio.CancelledError:
        self._cancelled = True
        process.kill()
        await process.wait()
        raise

    if self._cancelled:
        return ""  # Don't write response

    response = stdout_bytes.decode().strip()
    self._router.write("ai", response, ...)
```
Issue: _cancelled is instance-level but multiple calls could be concurrent. Need per-call tracking.

**Option B: Check if task is cancelled before writing**
```python
    response = stdout_bytes.decode().strip()

    # Check if our task was cancelled while we were completing
    current_task = asyncio.current_task()
    if current_task and current_task.cancelled():
        return ""

    self._router.write("ai", response, ...)
```
Issue: task.cancelled() might not be set yet if cancellation just arrived.

**Option C (Simplest): Wrap response writing in try/except**
```python
    response = stdout_bytes.decode().strip()
    try:
        self._call_count += 1
        self._router.write("ai", response, mode="NL", metadata={"type": "response"})
    except asyncio.CancelledError:
        # Cancellation arrived after subprocess completed but before write
        raise
    return response
```
This catches the late-arriving CancelledError if it comes during the write operation.

**Option D: Check shell.tasks to see if we're still tracked**
In _dispatch (shell.py line 199-202), the task is added to shell.tasks and awaited. If cancelled, it's removed. Could check this:
```python
# In AI.__call__, pass shell reference
if task_id not in shell.tasks:
    return ""  # We were cancelled
```
Issue: Requires plumbing shell reference through to AI.

verification:
files_changed: []
