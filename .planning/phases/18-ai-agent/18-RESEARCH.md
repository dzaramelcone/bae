# Phase 18: AI Agent - Research

**Researched:** 2026-02-13
**Domain:** AI callable object in REPL namespace -- NL conversation, bae LM bridge, code extraction, prompt engineering
**Confidence:** HIGH

## Summary

Phase 18 wires up the AI agent as a first-class Python object (`ai`) in the cortex namespace. The `ai` object is an async callable class with three entry points: `await ai("question")` for NL conversation with namespace context, `await ai.fill(NodeClass, context)` to invoke bae's LM fill directly, and `await ai.choose_type([A, B], ctx)` to invoke bae's LM choose_type. All output routes through the existing `[ai]` channel. The AI receives namespace context (referenced variables, graph topology, recent trace) when answering.

The key architectural decision is which LLM client to use for the NL conversation layer. Two options: (1) pydantic-ai `Agent` class, already a dependency, with built-in message history, streaming, and tool support; or (2) raw `anthropic.AsyncAnthropic` SDK, more control, less abstraction. The recommendation is **pydantic-ai Agent** because it is already installed, already used by `PydanticAIBackend`, handles conversation history via `message_history` parameter, and has a clean `run()`/`run_stream()` API. The existing `lm.py` already imports and uses pydantic-ai Agent. Using the same framework keeps the dependency surface minimal.

For `ai.fill()` and `ai.choose_type()`, these are thin wrappers around the existing bae LM protocol. The AI object holds a reference to an LM backend and delegates directly. No new LLM integration code is needed -- these methods call `lm.fill(target, resolved, instruction, source)` and `lm.choose_type(types, context)` respectively, which are already implemented on both PydanticAIBackend and ClaudeCLIBackend.

For code extraction (AI-06), the AI parses Python code blocks from its own NL output using a simple regex for triple-backtick fenced code blocks. This is a well-understood problem -- LLMs consistently use markdown code fences. A 4-line regex handles it. No external library needed.

For prompt engineering (AI-07), the system prompt is the critical artifact. It must instruct the AI to: (a) answer questions using the namespace context provided, (b) produce Python code when asked, (c) use bash/system calls when appropriate, and (d) ask clarifying questions when ambiguous. The system prompt is a static string configured at AI object construction.

**Primary recommendation:** Create `bae/repl/ai.py` with an `AI` callable class that wraps a pydantic-ai `Agent` for NL conversation and a bae `LM` backend for fill/choose_type. The AI object is placed in the namespace as `ai`. NL mode in `shell.py` dispatches to `await ai(text)` instead of the stub. Message history is maintained across the session via `AgentRunResult.new_messages()`.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `pydantic-ai` | 1.53.0 (installed) | `Agent` class for NL conversation -- `run()`, `run_stream()`, `message_history`, system_prompt | Already the LLM abstraction layer. Handles conversation, message history serialization, model selection. No new dependency. |
| `anthropic` | 0.77.1 (installed) | `AsyncAnthropic` available as fallback; `transform_schema` already used in lm.py | Transitive dependency via pydantic-ai. Not directly needed for Phase 18 but available. |
| `bae.lm` | internal | `LM.fill()` and `LM.choose_type()` for ai.fill/ai.choose_type delegation | Already implemented. Both PydanticAIBackend and ClaudeCLIBackend support these. |
| `bae.repl.channels` | internal | `ChannelRouter.write("ai", ...)` for all AI output | Already implemented in Phase 16. The `[ai]` channel exists with `#87d7ff` color. |
| `bae.repl.store` | internal | `SessionStore` for persisting AI output | Already integrated. Channels write to store automatically. |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `re` (stdlib) | 3.14 | Code block extraction from markdown-fenced LLM output | When AI produces code blocks in NL responses (AI-06). |
| `json` (stdlib) | 3.14 | Serializing namespace context for system prompt | When building context snapshot for AI. |
| `inspect` (stdlib) | 3.14 | `isclass()`, `isfunction()` for namespace context building | When summarizing namespace objects for the AI's system prompt. |
| `textwrap` (stdlib) | 3.14 | `dedent()` for system prompt formatting | System prompt string construction. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pydantic-ai Agent for NL | Raw `anthropic.AsyncAnthropic` | Raw SDK gives more control but requires manual message history management, no tool support, no retry logic. pydantic-ai is already a dependency and handles all of this. |
| pydantic-ai Agent for NL | Claude CLI subprocess (like ClaudeCLIBackend) | CLI subprocess is slow (process startup overhead per call), no streaming, no conversation history. Appropriate for structured output with --json-schema, not for NL chat. |
| Simple regex for code extraction | `parse-llm-code` PyPI package | External dependency for a 4-line regex. YAGNI. |
| Simple regex for code extraction | `mdextractor` PyPI package | Same -- external dependency for trivial parsing. |
| In-memory message history | Store-backed message history (SQLite) | Store persistence across sessions would be useful eventually but pydantic-ai's message format needs serialization. Start with in-memory (session-scoped). Persist via store entries (the channel already records all AI output). Cross-session history retrieval is a future enhancement. |

**Installation:**
```bash
# No new dependencies. All existing: pydantic-ai, anthropic SDK, bae internals.
```

## Architecture Patterns

### Recommended Project Structure

```
bae/repl/
    ai.py           # NEW: AI callable class, context builder, code extractor
    shell.py        # Modified: NL mode dispatches to ai(text), ai added to namespace
    namespace.py    # Unchanged (ai is injected in shell.py, like store and channels)
    channels.py     # Unchanged
    store.py        # Unchanged
    exec.py         # Unchanged
    bash.py         # Unchanged
    modes.py        # Unchanged
    complete.py     # Unchanged
```

### Pattern 1: AI as Async Callable Class

**What:** An `AI` class with `async def __call__(self, prompt)` for NL conversation, plus `fill()` and `choose_type()` methods that delegate to the bae LM backend. Placed in namespace as `ai`.

**When to use:** Every NL interaction and programmatic LM access from the REPL.

```python
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from pydantic_ai import Agent

if TYPE_CHECKING:
    from bae.lm import LM
    from bae.node import Node
    from bae.repl.channels import ChannelRouter

_CODE_BLOCK_RE = re.compile(
    r"```(?:python|py)?\s*\n(.*?)\n```",
    re.DOTALL,
)


class AI:
    """AI agent for natural language interaction with bae.

    await ai("question")                  -- NL conversation with context
    await ai.fill(NodeClass, context)     -- populate node via LM
    await ai.choose_type([A, B], context) -- pick successor type via LM
    """

    def __init__(
        self,
        *,
        lm: LM,
        router: ChannelRouter,
        namespace: dict,
        model: str = "anthropic:claude-sonnet-4-20250514",
    ) -> None:
        self._lm = lm
        self._router = router
        self._namespace = namespace
        self._history: list = []  # pydantic-ai message history
        self._agent = Agent(
            model,
            system_prompt=_build_system_prompt(),
        )

    async def __call__(self, prompt: str) -> str:
        """NL conversation with namespace context."""
        context = _build_context_message(self._namespace)
        full_prompt = f"{context}\n\nUser: {prompt}" if context else prompt

        result = await self._agent.run(
            full_prompt,
            message_history=self._history or None,
        )
        self._history = result.all_messages()
        response = result.output

        # Route through [ai] channel
        self._router.write("ai", response, mode="NL", metadata={"type": "response"})
        return response

    async def fill(self, target: type[Node], context: dict | None = None) -> Node:
        """Populate a node's plain fields via bae's LM fill."""
        resolved = context or {}
        instruction = target.__name__
        node = await self._lm.fill(target, resolved, instruction)
        return node

    async def choose_type(
        self, types: list[type[Node]], context: dict | None = None,
    ) -> type[Node]:
        """Pick successor type from candidates via bae's LM choose_type."""
        ctx = context or {}
        return await self._lm.choose_type(types, ctx)

    @staticmethod
    def extract_code(text: str) -> list[str]:
        """Extract Python code blocks from markdown-fenced text."""
        return _CODE_BLOCK_RE.findall(text)

    def __repr__(self) -> str:
        n = len(self._history)
        return f"ai -- await ai('question'). {n} messages in history."
```

**Confidence:** HIGH -- pydantic-ai Agent API verified. Message history via `result.all_messages()` confirmed working. `result.output` is the accessor for the response text.

### Pattern 2: Namespace Context Building

**What:** A function that summarizes the current namespace state into a context string for the AI's prompt. Includes: variable names and types, graph topology if a graph is loaded, recent trace if available.

**When to use:** Every `ai(prompt)` call -- the context is prepended to the user's prompt.

```python
import inspect
import json

from bae.graph import Graph
from bae.node import Node


def _build_context_message(namespace: dict) -> str:
    """Build a namespace context summary for the AI.

    Includes variable names/types, graph topology, and recent trace.
    Skips internal/private names and builtins.
    """
    parts: list[str] = []

    # Variable summary
    vars_summary = []
    for name, obj in sorted(namespace.items()):
        if name.startswith("_") or name == "__builtins__":
            continue
        if isinstance(obj, type):
            vars_summary.append(f"  {name}: class {obj.__name__}")
        elif isinstance(obj, Graph):
            vars_summary.append(f"  {name}: Graph(start={obj.start.__name__}, {len(obj.nodes)} nodes)")
        elif isinstance(obj, Node):
            vars_summary.append(f"  {name}: {type(obj).__name__}({_short_fields(obj)})")
        elif inspect.ismodule(obj):
            continue  # Skip modules -- not interesting context
        elif callable(obj):
            vars_summary.append(f"  {name}: callable")
        else:
            r = repr(obj)
            if len(r) > 80:
                r = r[:77] + "..."
            vars_summary.append(f"  {name}: {type(obj).__name__} = {r}")

    if vars_summary:
        parts.append("Namespace:\n" + "\n".join(vars_summary))

    # Graph topology
    graph = namespace.get("graph")
    if isinstance(graph, Graph):
        edges = []
        for node_cls in sorted(graph.nodes, key=lambda n: n.__name__):
            succs = graph.edges.get(node_cls, set())
            if succs:
                edges.append(f"  {node_cls.__name__} -> {', '.join(s.__name__ for s in succs)}")
            else:
                edges.append(f"  {node_cls.__name__} -> (terminal)")
        parts.append("Graph topology:\n" + "\n".join(edges))

    # Recent trace
    trace = namespace.get("_trace")
    if trace and isinstance(trace, list):
        trace_summary = [f"  {i+1}. {type(n).__name__}" for i, n in enumerate(trace[-5:])]
        parts.append("Recent trace (last 5):\n" + "\n".join(trace_summary))

    return "\n\n".join(parts) if parts else ""


def _short_fields(node: Node) -> str:
    """Short repr of node field values."""
    fields = node.model_dump()
    parts = []
    for k, v in fields.items():
        r = repr(v)
        if len(r) > 30:
            r = r[:27] + "..."
        parts.append(f"{k}={r}")
    return ", ".join(parts[:3])
```

**Confidence:** HIGH -- all introspection APIs verified in Phase 17 research. `Graph.nodes`, `Graph.edges`, `Node.model_dump()` all confirmed working.

### Pattern 3: System Prompt Engineering (AI-07)

**What:** A static system prompt that instructs the AI on its role within cortex. This is the critical prompt engineering artifact for reliable NL-to-code behavior.

**When to use:** Set once at AI construction via `Agent(system_prompt=...)`.

```python
def _build_system_prompt() -> str:
    """System prompt for the cortex AI agent."""
    return """\
You are the AI assistant inside cortex, a Python REPL built on bae (a framework for type-driven agent graphs).

Your role:
- Answer questions about the user's namespace, graphs, and code
- Produce correct Python code when asked
- Use bae's API correctly (Node, Graph, Dep, Recall, fill, choose_type)
- When asked to do system operations, suggest appropriate bash commands
- When ambiguous, ask clarifying questions rather than guessing

Context:
- You will receive the current namespace state with each message
- Variables, graphs, traces, and channel objects are all available
- The user can execute any Python you produce via the PY mode
- Code blocks should use ```python fences

bae quick reference:
- Nodes are Pydantic models: class MyNode(Node): field: str
- Graph topology from return types: async def __call__(self) -> NextNode | None: ...
- Dep(fn) for dependency injection, Recall() for trace recall
- graph = Graph(start=MyNode); result = await graph.arun(MyNode(field="value"), lm=lm)
- lm.fill(NodeClass, resolved_context, instruction) populates plain fields
- lm.choose_type([TypeA, TypeB], context) picks a successor type

Rules:
- Be concise. The REPL is a conversation, not documentation.
- When producing code, make it complete and directly executable.
- Use the namespace context to give specific, relevant answers.
- Never fabricate variable values -- only reference what's in the namespace.
"""
```

**Confidence:** MEDIUM -- prompt engineering is inherently iterative. This is a reasonable starting point but will need tuning based on actual usage. The key constraints (namespace awareness, code production, bae API reference) are correct.

### Pattern 4: NL Mode Integration in shell.py

**What:** Replace the NL mode stub in `shell.py` with a dispatch to `await ai(text)`. The AI object is created during `CortexShell.__init__` and placed in the namespace.

**When to use:** Every NL mode input.

```python
# In CortexShell.__init__():
from bae.repl.ai import AI
from bae.lm import PydanticAIBackend

lm = PydanticAIBackend()  # default LM for ai.fill/choose_type
self.ai = AI(lm=lm, router=self.router, namespace=self.namespace)
self.namespace["ai"] = self.ai

# In CortexShell.run(), NL mode handler:
elif self.mode == Mode.NL:
    try:
        response = await self.ai(text)
        # Response already routed through [ai] channel by AI.__call__
    except Exception:
        tb = traceback.format_exc()
        self.router.write("ai", tb.rstrip("\n"), mode="NL", metadata={"type": "error"})
```

**Confidence:** HIGH -- follows the exact same pattern as store/channels/ns integration from Phases 15-17.

### Pattern 5: Code Extraction (AI-06)

**What:** After the AI responds, the response text is checked for Python code blocks. If found, the extracted code is available for the user to execute or integrate.

**When to use:** After any AI response that might contain code.

```python
import re

_CODE_BLOCK_RE = re.compile(
    r"```(?:python|py)?\s*\n(.*?)\n```",
    re.DOTALL,
)


def extract_code(text: str) -> list[str]:
    """Extract Python code blocks from markdown-fenced text.

    Matches ```python, ```py, and bare ``` blocks.
    Returns list of code strings (without the fence markers).
    """
    return _CODE_BLOCK_RE.findall(text)
```

**Confidence:** HIGH -- this regex pattern is well-established for LLM output parsing. LLMs consistently use triple-backtick fences. Edge cases (nested backticks in strings) are rare in practice and not worth handling with a parser.

### Pattern 6: Conversation History Management

**What:** pydantic-ai's `Agent.run()` accepts `message_history` parameter. After each run, `result.all_messages()` returns the full conversation. Store this on the AI object for multi-turn context.

**When to use:** Every `ai(prompt)` call.

```python
# First call: no history
result = await self._agent.run(prompt)
self._history = result.all_messages()

# Subsequent calls: pass history
result = await self._agent.run(prompt, message_history=self._history)
self._history = result.all_messages()
```

**Confidence:** HIGH -- verified via pydantic-ai docs and API inspection. `message_history` parameter confirmed on `Agent.run()`. `all_messages()` returns `list[ModelMessage]` that can be passed back.

### Anti-Patterns to Avoid

- **Building a custom LLM client when pydantic-ai Agent exists:** pydantic-ai is already installed and used. Do not build a raw AsyncAnthropic wrapper for conversation -- Agent handles message formatting, history, retries, and model switching.
- **Modifying bae/lm.py for AI agent features:** The AI agent is a REPL concern. `ai.fill()` and `ai.choose_type()` delegate to the existing LM protocol. No changes to `bae/lm.py` or `bae/graph.py`.
- **Putting context in the system prompt:** The namespace context changes on every call. Put it in the user message, not the system prompt. The system prompt is static (role, rules, bae reference). Dynamic context goes in the message.
- **Auto-executing extracted code blocks:** AI-06 says "parse and extract" code, not "automatically execute" it. The extracted code should be presented to the user for review, or stored for explicit execution. Never auto-run LLM-generated code.
- **Making ai() synchronous:** The AI object must be async (`await ai("question")`). The REPL runs in an async event loop. Sync would block the loop.
- **Complex code extraction parser:** A regex for triple-backtick fences handles 99% of cases. Do not build an AST-based parser or use an external library for this.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| LLM conversation with history | Custom message formatting + HTTP calls | `pydantic_ai.Agent.run(message_history=...)` | Handles message format, history serialization, retry, model abstraction. Already a dependency. |
| Structured node population | Custom prompting logic for fill | `lm.fill(target, resolved, instruction)` | Already implemented on both backends (PydanticAIBackend, ClaudeCLIBackend). Tested. |
| Successor type selection | Custom prompting logic for choose_type | `lm.choose_type(types, context)` | Already implemented on both backends. Two-step approach (pick then fill) already handles oneOf avoidance. |
| Message history serialization | Custom serialization format | pydantic-ai `result.all_messages()` / `ModelMessagesTypeAdapter` | pydantic-ai provides typed message objects and serialization adapters. |
| Output channel routing | Custom print/display logic | `router.write("ai", response, mode="NL")` | Channel system from Phase 16 handles display, store persistence, visibility toggling. |
| Code block extraction | Parser library or AST-based extractor | `re.compile(r"```(?:python|py)?\s*\n(.*?)\n```", re.DOTALL)` | Simple, reliable regex. LLMs use standard markdown fences. |

**Key insight:** Phase 18 is an integration phase. The AI agent is a thin orchestration layer that connects existing pieces: pydantic-ai Agent for NL, bae LM for fill/choose_type, channels for output, store for persistence, namespace for context. The novel code is the system prompt and the context builder -- everything else is delegation.

## Common Pitfalls

### Pitfall 1: ANTHROPIC_API_KEY Not Available

**What goes wrong:** pydantic-ai Agent construction fails with `UserError: Set the ANTHROPIC_API_KEY environment variable...` if the key is not in the environment.

**Why it happens:** pydantic-ai's AnthropicProvider requires `ANTHROPIC_API_KEY` at construction time (verified in runtime test above).

**How to avoid:** Defer Agent construction until first use (lazy init), or catch the error at CortexShell init and print a clear message on the `[ai]` channel. The AI object can still be created -- just mark it as unavailable until a key is provided. Users can set `os.environ["ANTHROPIC_API_KEY"] = "sk-..."` in PY mode.

**Warning signs:** `pydantic_ai.exceptions.UserError` at shell startup.

### Pitfall 2: Context Message Too Large

**What goes wrong:** When the namespace has many objects (user-defined classes, large variables, loaded graphs), the context string prepended to every prompt balloons, consuming tokens and potentially exceeding context windows.

**Why it happens:** `_build_context_message` serializes all non-private namespace entries. A complex namespace could produce thousands of characters of context.

**How to avoid:** Truncate the context message to a reasonable limit (e.g., 2000 characters). Prioritize: (1) graph topology, (2) trace, (3) user-defined variables, (4) everything else. Skip bae types (Node, Graph, etc.) and module objects from the context -- the AI knows about these from its system prompt.

**Warning signs:** Slow AI responses, high token usage, or "context too long" errors.

### Pitfall 3: Message History Grows Unbounded

**What goes wrong:** After many turns of conversation, `self._history` contains the full message list, which grows without bound. Each subsequent `Agent.run()` call sends the entire history.

**Why it happens:** pydantic-ai's `all_messages()` returns all messages from all previous runs. No automatic pruning.

**How to avoid:** Limit history to the last N messages (e.g., 20). When history exceeds the limit, trim from the beginning but keep the first system prompt message. Alternatively, use a sliding window. The session store already captures all AI output persistently -- the in-memory history is for conversation context, not archival.

**Warning signs:** Increasing latency per AI call. Token usage climbing per turn.

### Pitfall 4: AI Response Not Appearing on [ai] Channel

**What goes wrong:** The AI response is returned but not displayed, or displayed on the wrong channel, or displayed twice (once by AI.__call__ and once by shell.py).

**Why it happens:** If both `AI.__call__` writes to the channel AND `shell.py` also writes, the response appears twice. If neither writes, it doesn't appear.

**How to avoid:** `AI.__call__` owns the channel write. It writes the response to the `[ai]` channel. `shell.py`'s NL mode handler should NOT write the response separately -- it only handles errors. This matches the PY mode pattern where `router.write("py", ...)` handles output and the handler only writes error tracebacks.

**Warning signs:** Duplicate `[ai]` output or missing `[ai]` output.

### Pitfall 5: ai.fill() Without LM Backend Configured

**What goes wrong:** `await ai.fill(MyNode, {})` fails because no LM backend is available (no API key, no model).

**Why it happens:** `AI.__init__` creates a default PydanticAIBackend which requires ANTHROPIC_API_KEY.

**How to avoid:** The LM backend used by ai.fill/choose_type should be the same one used by the graph runtime. If the user has configured an LM backend (e.g., `lm = ClaudeCLIBackend()`), the AI object should use that. Consider accepting an `lm` parameter at AI construction and allowing it to be swapped: `ai.lm = new_lm_backend`.

**Warning signs:** `UserError` or `RuntimeError` when calling ai.fill().

### Pitfall 6: async_exec Stdout Capture Interferes with ai()

**What goes wrong:** If `await ai("question")` is called from PY mode (e.g., user types `await ai("question")` in PY mode), the AI's channel write via `print_formatted_text` works correctly because channel writes bypass the stdout capture. However, the returned string value is also printed by PY mode's expression result handler.

**Why it happens:** PY mode captures expression results via `_` and displays them. `await ai("question")` returns a string, which PY mode will display as `repr(result)` on the `[py]` channel.

**How to avoid:** This is actually correct behavior -- the user called ai() from PY mode, and PY mode shows expression results. The AI response appears once on `[ai]` (via the channel write in AI.__call__) and the return value appears on `[py]` as a repr'd string. These are distinct outputs on distinct channels. The user can suppress the `[py]` output with `_ = await ai("question")` (assigns to _ but expression is assignment, not displayed). This is fine.

**Warning signs:** Users confused by seeing the AI response twice with different formatting.

## Code Examples

### Complete AI Class

```python
# bae/repl/ai.py
from __future__ import annotations

import inspect
import re
from typing import TYPE_CHECKING

from pydantic_ai import Agent

if TYPE_CHECKING:
    from bae.lm import LM
    from bae.node import Node
    from bae.repl.channels import ChannelRouter

_CODE_BLOCK_RE = re.compile(
    r"```(?:python|py)?\s*\n(.*?)\n```",
    re.DOTALL,
)

MAX_CONTEXT_CHARS = 2000
MAX_HISTORY_MESSAGES = 20


class AI:
    """AI agent for natural language interaction with bae."""

    def __init__(
        self,
        *,
        lm: LM,
        router: ChannelRouter,
        namespace: dict,
        model: str = "anthropic:claude-sonnet-4-20250514",
    ) -> None:
        self._lm = lm
        self._router = router
        self._namespace = namespace
        self._history: list = []
        self._agent: Agent | None = None
        self._model = model

    def _ensure_agent(self) -> Agent:
        """Lazy-init the pydantic-ai Agent (defers API key check)."""
        if self._agent is None:
            self._agent = Agent(self._model, system_prompt=_system_prompt())
        return self._agent

    async def __call__(self, prompt: str) -> str:
        """NL conversation with namespace context."""
        agent = self._ensure_agent()
        context = _build_context(self._namespace)
        full_prompt = f"{context}\n\n{prompt}" if context else prompt

        result = await agent.run(
            full_prompt,
            message_history=self._history[-MAX_HISTORY_MESSAGES:] or None,
        )
        self._history = result.all_messages()
        response = result.output
        self._router.write("ai", response, mode="NL", metadata={"type": "response"})
        return response

    async def fill(self, target: type[Node], context: dict | None = None) -> Node:
        """Populate a node's plain fields via bae's LM fill."""
        return await self._lm.fill(target, context or {}, target.__name__)

    async def choose_type(
        self, types: list[type[Node]], context: dict | None = None,
    ) -> type[Node]:
        """Pick successor type from candidates via bae's LM choose_type."""
        return await self._lm.choose_type(types, context or {})

    @staticmethod
    def extract_code(text: str) -> list[str]:
        """Extract Python code blocks from markdown-fenced text."""
        return _CODE_BLOCK_RE.findall(text)

    def __repr__(self) -> str:
        n = len(self._history)
        return f"ai -- await ai('question'). {n} messages in history."
```

### Shell Integration

```python
# In CortexShell.__init__():
from bae.repl.ai import AI
from bae.lm import PydanticAIBackend

lm = PydanticAIBackend()
self.ai = AI(lm=lm, router=self.router, namespace=self.namespace)
self.namespace["ai"] = self.ai

# In CortexShell.run(), NL mode handler:
elif self.mode == Mode.NL:
    try:
        await self.ai(text)
        # AI.__call__ handles channel output
    except Exception:
        tb = traceback.format_exc()
        self.router.write("ai", tb.rstrip("\n"), mode="NL", metadata={"type": "error"})
```

### Context Builder

```python
from bae.graph import Graph
from bae.node import Node


def _build_context(namespace: dict) -> str:
    """Summarize namespace for AI context, truncated to MAX_CONTEXT_CHARS."""
    parts = []

    # Graph topology (highest priority)
    graph = namespace.get("graph")
    if isinstance(graph, Graph):
        edges = []
        for n in sorted(graph.nodes, key=lambda x: x.__name__):
            succs = graph.edges.get(n, set())
            target = ", ".join(s.__name__ for s in succs) if succs else "(terminal)"
            edges.append(f"  {n.__name__} -> {target}")
        parts.append("Graph:\n" + "\n".join(edges))

    # Recent trace
    trace = namespace.get("_trace")
    if isinstance(trace, list) and trace:
        steps = [f"  {i+1}. {type(n).__name__}" for i, n in enumerate(trace[-5:])]
        parts.append("Trace:\n" + "\n".join(steps))

    # User variables (skip internals, modules, bae types, callables that are classes)
    skip = {"__builtins__", "ai", "ns", "store", "channels",
            "Node", "Graph", "Dep", "Recall", "GraphResult",
            "LM", "NodeConfig", "Annotated", "asyncio", "os"}
    user_vars = []
    for name, obj in sorted(namespace.items()):
        if name.startswith("_") or name in skip:
            continue
        if isinstance(obj, type) and issubclass(obj, Node):
            user_vars.append(f"  {name}: Node class")
        elif isinstance(obj, Node):
            user_vars.append(f"  {name}: {type(obj).__name__}")
        elif isinstance(obj, Graph):
            continue  # Already shown above
        elif not callable(obj):
            r = repr(obj)
            if len(r) > 60:
                r = r[:57] + "..."
            user_vars.append(f"  {name} = {r}")
    if user_vars:
        parts.append("Variables:\n" + "\n".join(user_vars))

    result = "\n\n".join(parts)
    if len(result) > MAX_CONTEXT_CHARS:
        result = result[:MAX_CONTEXT_CHARS] + "\n  ... (truncated)"
    return result
```

### Code Extraction Usage

```python
# In PY mode, user can extract and review code from AI responses:
#
# py> response = await ai("write a node that classifies sentiment")
# [ai] Here's a sentiment classification node:
# [ai] ```python
# [ai] class ClassifySentiment(Node):
# [ai]     text: str
# [ai]     sentiment: str = ""
# [ai]     confidence: float = 0.0
# [ai]
# [ai]     async def __call__(self) -> Positive | Negative | None:
# [ai]         ...
# [ai] ```
#
# py> blocks = ai.extract_code(response)
# py> blocks[0]
# 'class ClassifySentiment(Node):\n    text: str\n    ...'
#
# py> exec(blocks[0])  # User decides to execute
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual prompt construction per LLM call | pydantic-ai Agent with system_prompt and message_history | pydantic-ai 0.1+ (2024) | Conversation management abstracted away |
| Subprocess Claude CLI for every interaction | API-based pydantic-ai for NL, CLI reserved for structured output | Phase 18 design | Sub-second NL responses vs 5-10s CLI startup |
| No conversation history in REPL | Message history via `result.all_messages()` + `message_history` param | pydantic-ai 0.1+ (2024) | Multi-turn context maintained automatically |
| Manual code extraction from LLM text | Regex extraction of markdown code fences | Standard practice | Reliable with LLM markdown output conventions |
| REPL is code-only | NL is primary mode, AI lives in namespace | v4.0 cortex | Users interact via natural language first |

**Deprecated/outdated:**
- `result.data` accessor on pydantic-ai -- renamed to `result.output` (current version uses `.output`)
- Claude CLI for conversation -- too slow for interactive NL chat (5-10s per invocation)
- Manual anthropic SDK message formatting -- pydantic-ai handles this internally

## Open Questions

1. **Should the AI stream responses?**
   - What we know: pydantic-ai supports `Agent.run_stream()` which yields text tokens incrementally. The channel system writes complete strings.
   - What's unclear: Whether streaming provides meaningful UX improvement in a REPL where the user is waiting for the response anyway.
   - Recommendation: Start with `Agent.run()` (non-streaming). Streaming requires changes to the channel system to handle incremental writes and display. It can be added in a follow-up enhancement. YAGNI for Phase 18 MVP.

2. **Which LM backend should ai.fill/choose_type use?**
   - What we know: PydanticAIBackend and ClaudeCLIBackend both implement fill/choose_type. PydanticAIBackend is faster (API call vs subprocess). ClaudeCLIBackend uses constrained decoding (--json-schema).
   - What's unclear: Whether the user should be able to switch backends.
   - Recommendation: Default to PydanticAIBackend for the AI agent. Allow `ai._lm` to be reassigned by the user in PY mode for flexibility (`ai._lm = ClaudeCLIBackend()`). Eventually expose a clean `ai.lm` property.

3. **How should ai() handle ambiguity per AI-07?**
   - What we know: The success criteria says "handles ambiguity by asking." The system prompt instructs the AI to ask clarifying questions.
   - What's unclear: Whether the AI's clarifying question should be displayed as a normal response, or whether there should be a special "question" indicator.
   - Recommendation: A clarifying question is just another response routed through the `[ai]` channel. No special handling needed -- the system prompt does the work.

4. **Should extracted code blocks be auto-added to namespace?**
   - What we know: AI-06 says "parse Python code from NL conversation and integrate it into the codebase."
   - What's unclear: Whether "integrate" means auto-execute, offer to execute, or just make available.
   - Recommendation: Make available via `ai.extract_code(response)`. Do not auto-execute. The user can exec() the code in PY mode. Auto-execution of LLM-generated code is a safety concern and violates the principle that the user controls what runs.

5. **Should the AI have tools (pydantic-ai tool decorators)?**
   - What we know: pydantic-ai Agent supports `@agent.tool` for giving the LLM callable functions. This could enable the AI to execute code, query the store, or inspect graphs directly.
   - What's unclear: Whether Phase 18 scope includes tool use or just conversation.
   - Recommendation: No tools in Phase 18. The AI answers questions using the context provided in the message. Tool use (allowing the AI to call functions) is a significant expansion that should be a separate phase. It requires security considerations (what can the AI call?), error handling (what if the tool fails?), and UX design (how does tool use appear in output?).

6. **How should the AI agent handle startup when ANTHROPIC_API_KEY is missing?**
   - What we know: pydantic-ai Agent construction fails without the key.
   - What's unclear: Whether to fail silently, show a warning, or block.
   - Recommendation: Lazy-init the Agent (Pattern 1 above). The AI object is always created and placed in namespace. On first `await ai("question")`, if the key is missing, catch the error and display a clear message: "Set ANTHROPIC_API_KEY to use AI. In PY mode: os.environ['ANTHROPIC_API_KEY'] = 'sk-...'"

## Sources

### Primary (HIGH confidence)
- Existing codebase: `bae/lm.py` -- `PydanticAIBackend.fill()`, `.choose_type()`, Agent usage, `result.output` accessor (lines 233-354)
- Existing codebase: `bae/repl/shell.py` -- NL mode stub (line 169-171), channel integration pattern, namespace injection pattern
- Existing codebase: `bae/repl/channels.py` -- `ChannelRouter.write()`, `[ai]` channel with `#87d7ff` color
- Existing codebase: `bae/repl/namespace.py` -- `NsInspector` callable class pattern, `seed()` namespace dict
- Existing codebase: `bae/repl/store.py` -- `SessionStore.record()` via channels
- Existing codebase: `bae/repl/exec.py` -- `async_exec` with PyCF_ALLOW_TOP_LEVEL_AWAIT, stdout capture via StringIO
- Runtime verification: pydantic-ai 1.53.0 -- `Agent.__init__` params confirmed (`model`, `system_prompt`), `Agent.run()` params confirmed (`user_prompt`, `message_history`), return type `AgentRunResult` with `.output` field and `all_messages()` method
- Runtime verification: `anthropic` 0.77.1 -- `AsyncAnthropic` importable, available as fallback
- [pydantic-ai Agents documentation](https://ai.pydantic.dev/agent/) -- Agent API, system_prompt, run/run_stream
- [pydantic-ai Message History documentation](https://ai.pydantic.dev/message-history/) -- message_history parameter, all_messages(), new_messages(), ModelMessagesTypeAdapter
- [Anthropic SDK helpers.md](https://github.com/anthropics/anthropic-sdk-python/blob/main/helpers.md) -- AsyncAnthropic streaming API, text_stream, get_final_message

### Secondary (MEDIUM confidence)
- [pydantic-ai Function Tools](https://ai.pydantic.dev/tools/) -- @agent.tool pattern for future tool use
- [Anthropic SDK README](https://github.com/anthropics/anthropic-sdk-python/blob/main/README.md) -- AsyncAnthropic client, messages.create, messages.stream
- [pydantic-ai API reference](https://ai.pydantic.dev/api/agent/) -- detailed constructor and method signatures

### Tertiary (LOW confidence)
- Prompt engineering effectiveness -- system prompt quality is iterative, the initial version will need tuning based on real usage. LOW confidence that the first system prompt will be optimal.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- All existing dependencies. No new packages. pydantic-ai Agent API verified at runtime.
- Architecture: HIGH -- AI callable class follows established namespace object pattern (NsInspector, SessionStore, ChannelRouter). fill/choose_type delegation to existing LM protocol is trivial.
- Code extraction: HIGH -- Simple regex for markdown fences. Well-understood pattern.
- Prompt engineering: MEDIUM -- System prompt is a starting point. Will need iteration. The context builder is solid (uses verified introspection APIs from Phase 17).
- Pitfalls: HIGH -- API key handling, context size, history growth, channel output ownership all identified from understanding the existing codebase.

**Research date:** 2026-02-13
**Valid until:** 2026-03-15 (pydantic-ai API stable, anthropic SDK stable, bae internals unlikely to change)
