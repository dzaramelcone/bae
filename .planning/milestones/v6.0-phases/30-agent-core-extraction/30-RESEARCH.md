# Phase 30: Agent Core Extraction - Research

**Researched:** 2026-02-15
**Domain:** Internal refactoring -- extracting agent loop from REPL AI into shared module
**Confidence:** HIGH

## Summary

This phase extracts the multi-turn eval loop from `bae/repl/ai.py` into a standalone `bae/agent.py` module, then builds an `AgenticBackend` that implements the `LM` protocol using that core for tool-augmented `fill()`. The work is entirely internal to bae -- no external libraries, no new dependencies. The risk surface is well-bounded: the existing `AI.__call__` contains the complete eval loop (~100 lines), and the `LM` protocol is a 4-method `Protocol` class already used by `ClaudeCLIBackend`.

The key architectural insight is that the agent core is the eval loop (prompt -> Claude CLI -> extract `<run>` blocks -> execute Python -> feed output back -> loop) stripped of REPL coupling (no router, namespace persistence, store, label). The REPL AI becomes a thin wrapper adding those REPL concerns. The `AgenticBackend` wraps the same core but adds schema-constrained final extraction + per-node tool configuration.

**Primary recommendation:** Extract the eval loop as a pure async function (not a class) in `bae/agent.py`, parameterized by namespace, send function, and iteration limit. Both `AI.__call__` and `AgenticBackend.fill()` call it with different configurations.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| asyncio | stdlib | Subprocess management, async exec | Already used everywhere |
| re | stdlib | `<run>` block extraction | Already used in ai.py |
| pydantic | (project dep) | Schema generation for constrained output | Already used by `_build_plain_model` |

### Supporting
No new dependencies needed. This is pure refactoring of existing code.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Function-based core | Class-based AgentCore | Class adds unnecessary state; the loop is stateless per-invocation. Namespace and send-fn are injected per call. |
| Claude CLI subprocess | Direct API calls | CLI is the established pattern in bae. Switching transport is a separate concern. |

## Architecture Patterns

### Current Structure (before)
```
bae/
  repl/
    ai.py          # AI class: eval loop + REPL coupling + tool tags + _send
  lm.py            # LM protocol + ClaudeCLIBackend (no tools, no agency)
```

### Target Structure (after)
```
bae/
  agent.py         # agent_loop() -- pure eval loop, no REPL coupling
  repl/
    ai.py          # AI wraps agent_loop + router + namespace + store + session
  lm.py            # LM protocol + ClaudeCLIBackend + AgenticBackend
```

### Pattern 1: Extract eval loop as async generator or coroutine

**What:** The eval loop in `AI.__call__` (lines 100-202) follows a clear pattern: send prompt -> get response -> extract code -> execute -> build feedback -> loop. Extract this as a standalone async function.

**When to use:** When the same loop logic needs different wrappers (REPL vs headless agent).

**Boundaries to extract:**
```python
# What belongs in agent_loop():
# 1. Send prompt to Claude CLI (parameterized send function)
# 2. Extract <run> blocks from response
# 3. Execute Python in namespace (parameterized namespace)
# 4. Build feedback string from output
# 5. Loop until no more code blocks or max_iters
# 6. Return final response

# What stays in AI.__call__():
# 1. Cross-session context (store)
# 2. _build_context(namespace) for REPL state summary
# 3. router.write() calls for display
# 4. Label and metadata management

# What goes in AgenticBackend.fill():
# 1. Build prompt from target type + resolved deps
# 2. Seed namespace with useful imports
# 3. Run agent_loop() with iteration cap
# 4. Extract structured JSON from final response
# 5. Validate through Pydantic plain model
```

### Pattern 2: AgenticBackend as LM protocol implementation

**What:** `AgenticBackend` implements `LM` (same 4 methods as `ClaudeCLIBackend`) but uses agent_loop for fill(). The `choose_type()`, `make()`, and `decide()` methods can delegate to a wrapped `ClaudeCLIBackend` (no tools needed for type selection).

**When to use:** When a node needs tool use during field population (research, web scraping, code generation).

**Integration point -- NodeConfig:**
```python
class ResearchNode(Node):
    node_config: ClassVar[NodeConfig] = NodeConfig(lm=AgenticBackend())

    findings: str   # AgenticBackend uses tools to populate this
```

Note: `node_config` is already defined on `Node` but the graph engine (`graph.py`) does NOT currently read it. The `arun()` loop always uses the graph-level `lm`. This means Phase 30 must either:
- (a) Wire `node_config["lm"]` lookup into `graph.py`'s `arun()`, OR
- (b) Accept that `AgenticBackend` is only usable as the graph-level LM for now

Option (a) is the correct path but touches `graph.py` which is being modified by another agent. Coordinate or defer.

### Pattern 3: Namespace seeding for headless agent

**What:** The agent core needs a fresh namespace per run, seeded with useful imports but no REPL state.

**Existing pattern (REPL):** `bae/repl/namespace.py` seeds with bae types (Node, Graph, Dep, etc.) + asyncio + os.

**Agent pattern:** Seed with practical imports for tool use:
```python
def _agent_namespace() -> dict:
    """Fresh namespace for agentic execution -- no REPL state."""
    import httpx, json, pathlib, re, os
    return {
        "__builtins__": __builtins__,
        "httpx": httpx,
        "json": json,
        "Path": pathlib.Path,
        "re": re,
        "os": os,
    }
```

### Anti-Patterns to Avoid
- **Shared mutable namespace across runs:** Each `AgenticBackend.fill()` call must get a fresh namespace. Leaking state between nodes would cause unpredictable behavior.
- **Putting tool tag logic in agent core:** Tool tags (`<R:path>`, `<W:path>`, etc.) are REPL sugar. The agent core should only handle `<run>` blocks. The REPL wrapper adds tool tag handling on top.
- **Making agent core a class with persistent state:** The eval loop is stateless per invocation. Session persistence (Claude CLI `--resume`) belongs in the wrapper, not the core.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Python execution with stdout capture | New exec function | `bae/repl/exec.py` `async_exec()` | Already handles top-level await, stdout capture, last-expr result |
| `<run>` block extraction | New regex | `AI.extract_executable()` (move to module level) | Already tested, handles edge cases |
| Schema building for constrained output | Custom schema builder | `_build_plain_model()` + `transform_schema()` from `bae/lm.py` | Already handles nested models, format stripping |
| CLI subprocess management | New subprocess wrapper | Adapt `_send()` pattern from `AI._send()` | Handles timeout, cancellation, env sanitization |

**Key insight:** Nearly every component needed already exists in `bae/repl/ai.py` or `bae/lm.py`. The work is decomposition and reassembly, not invention.

## Common Pitfalls

### Pitfall 1: Breaking REPL AI by over-extracting
**What goes wrong:** Extracting too much into agent core makes REPL AI unable to do its job (e.g., extracting session management, tool tag handling).
**Why it happens:** Temptation to make the core "complete" rather than minimal.
**How to avoid:** The core handles ONLY: send -> extract `<run>` -> execute -> feedback -> loop. Everything else stays in the wrapper. Tool tags are REPL-only. Session persistence is REPL-only.
**Warning signs:** Core function has parameters for router, store, or label.

### Pitfall 2: Namespace pollution in AgenticBackend
**What goes wrong:** Agent writes to namespace during fill(), and those side effects leak across nodes or runs.
**Why it happens:** Reusing namespace dict across calls, or seeding with mutable shared objects.
**How to avoid:** Create fresh namespace per `fill()` call. Never share namespace between invocations.
**Warning signs:** Second fill() call sees variables from first call.

### Pitfall 3: Extracting structured output from agentic response
**What goes wrong:** After multi-turn tool use, the agent's final response is natural language, not JSON. Extracting the structured output requires a final constrained-output call.
**Why it happens:** Agent loop produces prose; structured output requires schema constraints.
**How to avoid:** After agent loop completes, make one final `_run_cli_json()` call with the plain model schema, passing the agent's accumulated context as prompt. This is the "agentic fill then structured extract" two-phase pattern.
**Warning signs:** Trying to parse JSON from the agent's natural language response.

### Pitfall 4: Claude CLI session conflicts
**What goes wrong:** AgenticBackend uses `--session-id` / `--resume` just like REPL AI, causing "already in use" lock errors if both run concurrently.
**Why it happens:** Claude CLI sessions are process-locked.
**How to avoid:** AgenticBackend should use `--no-session-persistence` (like ClaudeCLIBackend does) since it doesn't need cross-call memory. Each fill() is self-contained.
**Warning signs:** "Session already in use" errors during graph execution.

### Pitfall 5: Coordinating with graph.py changes
**What goes wrong:** Phase 30 touches `graph.py` to wire `node_config` LM lookup, but another agent is modifying `graph.py` for engine work.
**Why it happens:** Parallel phase execution on overlapping files.
**How to avoid:** Either (a) defer `node_config` wiring to a later phase, or (b) coordinate with the other agent's changes. The `AgenticBackend` can be built and tested standalone without graph integration.
**Warning signs:** Merge conflicts in `graph.py`.

## Code Examples

### Existing eval loop structure (from AI.__call__)
```python
# bae/repl/ai.py lines 100-202 -- the loop to extract
response = await self._send(full_prompt)

while not self._max_eval_iters or _iters < self._max_eval_iters:
    _iters += 1
    # Tool tags (REPL-only, stays in wrapper)
    tool_results = run_tool_calls(response)
    if tool_results:
        # ... handle tool tags, feed back, continue
        continue

    # <run> blocks (goes into agent core)
    code, extra = self.extract_executable(response)
    if code is None:
        break

    # Execute
    result, captured = await async_exec(code, self._namespace)
    # ... handle output, build feedback

    response = await self._send(feedback)
```

### Extracted agent core signature
```python
# bae/agent.py

async def agent_loop(
    prompt: str,
    *,
    send: Callable[[str], Awaitable[str]],
    namespace: dict,
    max_iters: int = 10,
) -> str:
    """Multi-turn eval loop: prompt -> response -> extract <run> -> execute -> loop.

    Args:
        prompt: Initial prompt to send.
        send: Async function that sends prompt text and returns response text.
        namespace: Python namespace for code execution.
        max_iters: Maximum eval iterations (0 = unlimited).

    Returns:
        Final response text after all code blocks are resolved.
    """
```

### REPL AI wrapping the core
```python
# bae/repl/ai.py (after refactor)

async def __call__(self, prompt: str) -> str:
    # REPL-specific: build context, cross-session, etc.
    full_prompt = self._build_full_prompt(prompt)

    # Agent core does the loop
    response = await agent_loop(
        full_prompt,
        send=self._send,
        namespace=self._namespace,
        max_iters=self._max_eval_iters,
    )

    # REPL-specific: tool tag pass on each response
    # (tool tags need router integration, so they wrap agent_loop
    #  or are handled in an outer loop around agent_loop)
    return response
```

Note: The REPL AI's tool tag handling (`run_tool_calls`) happens at the same level as `<run>` block extraction. Both are "things to do with the response before looping." The cleanest extraction is:
- Agent core handles `<run>` blocks only (the universal tool system)
- REPL AI adds a pre-check for tool tags before delegating to the core, OR
- REPL AI wraps the core in an outer loop that handles tool tags

### AgenticBackend.fill()
```python
# bae/lm.py (AgenticBackend added)

class AgenticBackend:
    """LM backend with multi-turn tool use during fill().

    Uses agent_loop for research/tool calls, then extracts
    structured output via constrained decoding.
    """

    def __init__(self, model: str = "claude-opus-4-6", max_iters: int = 5):
        self.model = model
        self.max_iters = max_iters
        self._cli = ClaudeCLIBackend(model=model)  # for structured extraction

    async def fill(self, target, resolved, instruction, source=None):
        prompt = _build_fill_prompt(target, resolved, instruction, source)
        prompt += "\n\nUse Python to research and gather information, then provide your answer."

        namespace = _agent_namespace()

        async def send(text: str) -> str:
            # Single-shot Claude CLI call (no session persistence)
            return await _cli_send(text, model=self.model)

        # Phase 1: Agentic research
        final_response = await agent_loop(
            prompt, send=send, namespace=namespace, max_iters=self.max_iters
        )

        # Phase 2: Structured extraction
        plain_model = _build_plain_model(target)
        schema = transform_schema(plain_model)
        extraction_prompt = f"Based on your research:\n{final_response}\n\nExtract the data."
        data = await self._cli._run_cli_json(extraction_prompt, schema)

        validated = validate_plain_fields(data, target)
        all_fields = dict(resolved)
        all_fields.update(validated)
        return target.model_construct(**all_fields)

    async def choose_type(self, types, context):
        return await self._cli.choose_type(types, context)

    async def make(self, node, target):
        return await self._cli.make(node, target)

    async def decide(self, node):
        return await self._cli.decide(node)
```

### _send without session persistence (for AgenticBackend)
```python
async def _cli_send(prompt: str, *, model: str, timeout: int = 60) -> str:
    """Single-shot Claude CLI call without session persistence."""
    cmd = [
        "claude", "-p", prompt,
        "--model", model,
        "--output-format", "text",
        "--tools", "",
        "--strict-mcp-config",
        "--setting-sources", "",
        "--no-session-persistence",
    ]
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    process = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env,
    )
    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    if process.returncode != 0:
        raise RuntimeError(f"Claude CLI failed: {stderr.decode()}")
    return stdout.decode().strip()
```

Wait -- this won't work for multi-turn. Without `--resume`, each `send()` call in the agent loop loses conversation history. The REPL AI handles this via `--session-id` / `--resume`. The AgenticBackend needs session management too, but ephemeral (per fill() call).

**Corrected pattern:**
```python
async def fill(self, target, resolved, instruction, source=None):
    session_id = str(uuid.uuid4())  # ephemeral session
    call_count = 0

    async def send(text: str) -> str:
        nonlocal call_count
        cmd = ["claude", "-p", text, "--model", self.model, ...]
        if call_count == 0:
            cmd += ["--session-id", session_id, "--system-prompt", AGENT_PROMPT]
        else:
            cmd += ["--resume", session_id]
        call_count += 1
        # ... subprocess exec

    final_response = await agent_loop(prompt, send=send, namespace=namespace, ...)
```

This means the `send` function encapsulates session state. The agent core doesn't know about sessions.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `make`/`decide` (v1 API) | `choose_type`/`fill` (v2 API) | Phase 6-7 | fill() is where AgenticBackend slots in |
| Monolithic AI class | Extracted core + wrapper | Phase 30 (this) | Enables headless agent use |

## Open Questions

1. **Tool tag handling in REPL AI wrapper**
   - What we know: Tool tags (`<R:path>`, etc.) are checked before `<run>` blocks in the current loop. They need `router.write()` for display.
   - What's unclear: Should the REPL wrapper intercept responses BEFORE passing to agent_loop, or wrap agent_loop in an outer loop? The current code checks tool tags first, then falls through to `<run>` blocks.
   - Recommendation: Keep tool tags in the REPL AI wrapper. The wrapper runs an outer loop: check tool tags -> if found, handle + send feedback + continue. Only when no tool tags are found, delegate to agent_loop for `<run>` block handling. This cleanly separates REPL sugar from the universal agent core.

2. **node_config wiring in graph.py**
   - What we know: `NodeConfig` has an `lm` key. `Node.node_config` is a ClassVar. The graph engine ignores it.
   - What's unclear: Whether graph.py changes should be in this phase or deferred (graph.py is being modified by another agent).
   - Recommendation: Build `AgenticBackend` standalone and test it directly (not through graph). Defer `node_config` wiring to avoid graph.py conflicts. Document the wiring needed.

3. **System prompt for AgenticBackend**
   - What we know: REPL AI uses `ai_prompt.md` with REPL-specific instructions. ClaudeCLIBackend uses a one-liner "structured data generator" prompt.
   - What's unclear: What system prompt should the agentic backend use?
   - Recommendation: A minimal prompt: "You are a research agent. Use Python to gather information. Write code in `<run>` tags." No REPL-specific instructions (no `ns()`, no `store`, no file tags). Keep it focused on the task.

4. **extract_executable as module-level function**
   - What we know: `AI.extract_executable` is a `@staticmethod` that uses `_EXEC_BLOCK_RE`. The agent core needs it too.
   - What's unclear: Where should it live?
   - Recommendation: Move to `bae/agent.py` as a module-level function. AI.extract_executable becomes a thin wrapper or direct import. The regex `_EXEC_BLOCK_RE` moves with it.

5. **AgenticBackend location**
   - What we know: The design says `bae/lm.py` since it implements the `LM` protocol.
   - What's unclear: `bae/lm.py` is already 517 lines. Adding AgenticBackend would grow it further.
   - Recommendation: Put `AgenticBackend` in `bae/agent.py` alongside the core loop. It imports from `bae/lm.py` what it needs (`_build_plain_model`, `transform_schema`, etc.). Export it from `bae/__init__.py`. This keeps `lm.py` focused on the non-agentic LM protocol and `agent.py` as the agentic module.

## Sources

### Primary (HIGH confidence)
- `bae/repl/ai.py` -- complete eval loop implementation (lines 100-202), tool tag system, `_send` method
- `bae/lm.py` -- LM protocol (4 methods), ClaudeCLIBackend implementation, fill helpers
- `bae/node.py` -- Node base class, NodeConfig TypedDict, `_wants_lm`
- `bae/resolver.py` -- field classification, dep resolution, LM_KEY sentinel
- `bae/graph.py` -- graph execution loop, routing strategies, LM usage
- `bae/repl/exec.py` -- `async_exec()` for Python execution with stdout capture
- `bae/repl/namespace.py` -- namespace seeding pattern
- `bae/repl/channels.py` -- ChannelRouter used by AI for output display

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, pure internal refactoring
- Architecture: HIGH -- all components exist and are well-understood from source
- Pitfalls: HIGH -- identified from direct code analysis, not speculation

**Research date:** 2026-02-15
**Valid until:** 2026-03-15 (stable -- internal refactoring, no external deps to go stale)
