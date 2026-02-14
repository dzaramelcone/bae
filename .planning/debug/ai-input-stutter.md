---
status: resolved
trigger: "AI (NL mode) tasks cause input stuttering/lag, Ctrl-C unresponsive during NL tasks"
created: 2026-02-14T00:00:00Z
updated: 2026-02-14T00:00:00Z
---

## Current Focus

hypothesis: CONFIRMED -- AI subprocess inherits parent stdin, causing terminal contention with prompt_toolkit
test: Compare ai.py vs bash.py subprocess creation; analyze stdin fd inheritance semantics
expecting: ai.py missing stdin=DEVNULL
next_action: Document fix

## Symptoms

expected: Typing in REPL stays responsive while AI NL task runs in background; Ctrl-C opens task menu immediately
actual: Input stutters, lags, keystrokes dropped/ignored during AI subprocess execution; Ctrl-C unresponsive
errors: No error messages -- behavioral degradation only
reproduction: Enter NL mode, submit any query, try typing or pressing Ctrl-C while AI is processing
started: Since NL mode was implemented -- inherent in the subprocess spawning

## Eliminated

(none -- first hypothesis was correct)

## Evidence

- timestamp: 2026-02-14
  checked: ai.py line 84-89 subprocess creation
  found: |
    ```python
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        start_new_session=True,
    )
    ```
    No `stdin=` parameter. Defaults to None, which inherits parent's stdin fd.
  implication: Claude CLI subprocess shares the terminal's stdin with prompt_toolkit

- timestamp: 2026-02-14
  checked: bash.py line 28-34 subprocess creation
  found: |
    Also missing stdin= parameter, but bash commands are short-lived (ms-seconds)
    and don't actively read stdin, so contention window is negligible.
  implication: Explains why bash mode doesn't exhibit the same stutter

- timestamp: 2026-02-14
  checked: asyncio.create_subprocess_exec default behavior
  found: |
    When stdin param is None (the default), the subprocess inherits the parent
    process's stdin file descriptor (fd 0). Both parent and child can read from
    the same terminal device simultaneously.
  implication: Classic stdin contention -- two readers on one fd

- timestamp: 2026-02-14
  checked: start_new_session=True effect on stdin
  found: |
    setsid() creates new process group/session and detaches the controlling
    terminal association, but does NOT close or redirect inherited fds.
    The stdin fd is still open and readable by the child.
  implication: start_new_session does not prevent stdin contention

- timestamp: 2026-02-14
  checked: Claude CLI behavior with -p flag
  found: |
    Claude CLI is a Node.js interactive tool. Even with -p (print mode), the
    process inherits stdin and may probe terminal capabilities, hold the fd
    open, or perform reads. It runs for 10-60+ seconds per query.
  implication: Long-running process + inherited stdin = sustained contention with prompt_toolkit's raw mode terminal input

- timestamp: 2026-02-14
  checked: prompt_toolkit architecture
  found: |
    prompt_async() puts the terminal in raw mode and reads stdin via its own
    event loop. When another process also has stdin fd open, it can steal
    bytes (keystrokes), change terminal attributes, or block reads.
  implication: This is why keystrokes are dropped and Ctrl-C doesn't register

## Resolution

root_cause: |
  `bae/repl/ai.py` line 84 spawns the Claude CLI subprocess without specifying
  `stdin=asyncio.subprocess.DEVNULL`. This causes the child process to inherit
  the parent's stdin file descriptor (fd 0) -- the terminal.

  prompt_toolkit's `prompt_async()` also reads from the same terminal stdin in
  raw mode. Two processes reading from the same terminal fd causes contention:
  the subprocess can steal keystrokes, disrupt raw mode, and block reads.

  The Claude CLI runs for 10-60+ seconds per NL query, creating a sustained
  window of contention. Bash commands don't exhibit this because they're
  short-lived and rarely read stdin.

fix: |
  Add `stdin=asyncio.subprocess.DEVNULL` to the subprocess creation in ai.py:

  ```python
  process = await asyncio.create_subprocess_exec(
      *cmd,
      stdin=asyncio.subprocess.DEVNULL,  # prevent stdin contention with prompt_toolkit
      stdout=asyncio.subprocess.PIPE,
      stderr=asyncio.subprocess.PIPE,
      env=env,
      start_new_session=True,
  )
  ```

  The Claude CLI with -p flag doesn't need stdin (prompt is passed via args).
  DEVNULL gives it /dev/null as stdin, eliminating contention entirely.

  Consider also adding stdin=asyncio.subprocess.DEVNULL to bash.py for
  consistency, though it's lower priority since bash commands are short-lived.

verification: applied and committed
files_changed:
  - bae/repl/ai.py (cd66894 -- stdin=DEVNULL + 28ea212 -- session reset after cancel)
  - bae/repl/bash.py (cd66894 -- stdin=DEVNULL defensive consistency)
