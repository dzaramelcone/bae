# Phase 14: Shell Foundation - Context

**Gathered:** 2026-02-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Async REPL with four modes (NL, Py, Graph, Bash), good text editing in Py mode, and clean lifecycle (launch, interrupt, shutdown). This is the first v4.0 phase -- no AI agent, no session store, no channels yet. NL and Graph modes are stubs. The REPL is the central Python process; bash commands shell out via subprocess.

</domain>

<decisions>
## Implementation Decisions

### Prompt & mode identity
- Clean minimal prompt: `> ` style, no mode name in the prompt itself
- Mode indicated by prompt color -- each mode has a distinct color (NL, Py, Graph, Bash)
- Bottom status bar (persistent, like vim) shows: active mode name + working directory
- No keybinding hints or help text in the status bar -- users learn from docs

### Multiline editing
- Enter submits, Shift+Enter inserts newline -- consistent across ALL modes
- Auto-indentation in Py mode: Claude's discretion (smart indent or basic, whatever prompt_toolkit does well)
- Tab completion in Py mode: Claude's discretion (pick what prompt_toolkit supports cleanly)
- Syntax highlighting in Py mode (per spec)

### Launch
- `bae` with no arguments launches cortex -- silent start, straight to prompt, no banner
- Default mode is NL (even though NL is a stub in Phase 14)
- No CLI arguments in Phase 14 -- `bae` launches the REPL, period
- No in-REPL help/discovery mechanism

### Bash mode execution model
- The REPL owns a cwd; bash commands execute via Python subprocess inheriting that cwd
- `cd` is special-cased: updates the REPL's working directory (os.chdir), affects all modes
- Each non-cd bash command spawns a subprocess, returns stdout/stderr
- Stderr displayed in red, stdout plain
- User navigates the OS and spawns processes through bash mode; results flow back to the REPL
- No shell state carries over between commands (env vars, aliases) -- each is a fresh subprocess

### Mode stubs
- Graph mode: exists in the mode cycle (Shift+Tab reaches it), but input is a no-op/stub message
- NL mode: exists and is the default; Claude's discretion on stub behavior (echo, pass-to-py fallback, or stub message)

### Shutdown & interrupt
- Ctrl-C with nothing running: single press exits immediately, no confirmation
- Ctrl-C while code is running in Py mode: raises KeyboardInterrupt (standard Python behavior), does NOT exit the REPL
- Ctrl-D: graceful shutdown -- cancels tasks, drains queues, brief summary line (`cancelled N tasks`), then exits
- Ctrl-D with nothing running: silent exit, straight back to shell
- Unhandled exceptions in Py mode: standard Python traceback (full, familiar)

### Claude's Discretion
- Auto-indentation approach in Py mode (smart vs basic -- whatever prompt_toolkit does well)
- Tab completion depth (namespace + builtins vs Jedi-style -- pick what works)
- NL mode stub behavior before Phase 18 wires up the AI agent
- Prompt colors per mode
- Status bar styling

</decisions>

<specifics>
## Specific Ideas

- "The REPL is the central process" -- bash mode shells out via subprocess, everything returns to the REPL. Seamless mode switching with shared cwd.
- Completion architecture should have a clean provider interface -- language server (LSP) integration for both user and AI channels is a future goal and the design should not preclude it.

</specifics>

<deferred>
## Deferred Ideas

- Language server (LSP) integration for completion (both user typing and AI code generation) -- future phase
- CLI arguments (`bae py`, `bae -c 'expr'`) -- future phase
- In-REPL help system -- future phase or docs

</deferred>

---

*Phase: 14-shell-foundation*
*Context gathered: 2026-02-13*
