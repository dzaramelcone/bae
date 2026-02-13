# Technology Stack: v4.0 Cortex REPL

**Project:** Bae - Type-driven agent graphs with DSPy optimization
**Researched:** 2026-02-13
**Focus:** Stack additions for the cortex augmented async Python REPL -- prompt_toolkit REPL shell, OTel spans for context, channel-based I/O, reflective namespace introspection
**Overall confidence:** HIGH for prompt_toolkit and OTel; HIGH for stdlib channels (no external lib needed); HIGH for introspection (Python 3.14 stdlib)

---

## Executive Summary

Cortex needs **2 new runtime dependencies** (prompt_toolkit, opentelemetry-sdk) and **1 new dev dependency** (pygments). Everything else is Python 3.14 stdlib or already a transitive dependency of pydantic-ai.

The key architectural insight: **do not add a channel library**. Python 3.14's `asyncio.Queue` gained `.shutdown()` in 3.13, which is the one feature aiochannel had over bare queues. Labeled channels are a thin wrapper (dict of str to Queue) -- 20 lines, not a dependency. Similarly, **do not add typing-inspect or typing-inspection** -- Python 3.14's `annotationlib` module (PEP 649/749) plus the existing `inspect.get_annotations()` and `typing.get_type_hints()` provide everything the reflective namespace needs.

`opentelemetry-api` is already a transitive dependency via `pydantic-ai-slim>=1.28.0`. We need `opentelemetry-sdk` explicitly for `TracerProvider`, `SimpleSpanProcessor`, and `InMemorySpanExporter` -- the machinery that creates, processes, and stores spans. The API alone only provides the interface stubs.

prompt_toolkit 3.0.52 is native asyncio (since 3.0). `PromptSession.prompt_async()` integrates directly into the existing event loop. `patch_stdout()` prevents concurrent output (graph execution, AI responses) from corrupting the prompt. `Application.create_background_task()` manages coroutines tied to the application lifecycle. This is the foundation for the three-mode REPL (NL/Py/Graph).

---

## Recommended Stack Changes

### Add (runtime)

| Package | Version | Purpose | Why This, Why Now |
|---------|---------|---------|-------------------|
| `prompt_toolkit` | >=3.0.50 | Async REPL shell with custom key bindings, lexer, completer | Native asyncio since 3.0. `PromptSession.prompt_async()` runs inside the existing event loop without blocking. `patch_stdout()` handles concurrent output from graph execution. Custom `Lexer` + `KeyBindings` enable mode switching (NL/Py/Graph). Only dep is `wcwidth`. Decision was made NOT to use IPython -- prompt_toolkit is what IPython itself is built on, minus the 50MB of unneeded weight. |
| `opentelemetry-sdk` | >=1.39 | Span creation, processing, in-memory storage | `opentelemetry-api` is already a transitive dep of `pydantic-ai-slim`. But the API is just interfaces -- `TracerProvider`, `SimpleSpanProcessor`, `InMemorySpanExporter` live in the SDK. Cortex needs spans as **first-class context objects** (not just telemetry export), so we need programmatic access to span data via `InMemorySpanExporter.get_finished_spans()`. Transitive deps: `opentelemetry-api`, `opentelemetry-semantic-conventions`, `typing-extensions` -- all already present. |

### Add (dev only)

| Package | Version | Purpose | Why |
|---------|---------|---------|-----|
| `pygments` | >=2.19 | Python syntax highlighting in REPL | prompt_toolkit's `PygmentsLexer` wraps any Pygments lexer. We need `PythonLexer` for Py mode syntax highlighting. Already a transitive dep of `rich` (which is transitive via `typer`), but making it explicit in dev deps ensures the import works. Zero additional download. |

### Keep (leverage differently for v4)

| Package | Current | v4 Role |
|---------|---------|---------|
| `pydantic>=2.0` | 2.12.5 | Namespace objects as Pydantic models; `model_dump()` for span attributes; `model_json_schema()` for AI context |
| `pydantic-ai>=0.1` | 1.54.0 | AI agent object in namespace; `Agent.instrument_all()` auto-instruments LLM calls with OTel spans that cortex can capture |
| `typer>=0.12` | 0.21.1 | `bae cortex` CLI entry point launches the REPL |
| `asyncio` (stdlib) | 3.14 | `asyncio.Queue` with `.shutdown()` for channels; `asyncio.create_task()` for background graph execution; `contextvars` for span propagation across tasks |

### Do NOT Add

| Temptation | Why Not | What Instead |
|------------|---------|--------------|
| **IPython / ipykernel** | 50MB+ install. Custom kernel protocol is complex. We need a thin REPL with mode switching, not a notebook kernel. IPython's own REPL is built on prompt_toolkit -- we go one layer deeper for control. | prompt_toolkit `PromptSession` with custom lexer, completer, key bindings. |
| **aiochannel** | Only advantage over `asyncio.Queue` was closable channels. Python 3.13+ added `Queue.shutdown()` which does exactly this. `QueueShutDown` exception on get/put after shutdown. aiochannel is 69 commits, 41 stars -- not worth the dep for something stdlib now covers. | `asyncio.Queue` with `.shutdown()`. Labeled channels = `dict[str, asyncio.Queue]`. |
| **trio / anyio** | Bae is asyncio-native throughout (resolver uses `asyncio.gather`, graph uses `asyncio.create_subprocess_exec`). Adding an async compatibility layer adds complexity for zero gain. | Pure asyncio. |
| **typing-inspect / typing-inspection** | Python 3.14's `annotationlib` module (PEP 649/749) provides `get_annotations()` with `Format.VALUE`, `Format.FORWARDREF`, `Format.STRING`. Bae already uses `typing.get_type_hints()` everywhere. No gap to fill. | `annotationlib.get_annotations()` + `typing.get_type_hints()` + `inspect` module. |
| **rich** (for REPL output) | prompt_toolkit has its own rendering pipeline (`FormattedText`, `print_formatted_text`, ANSI support). Mixing Rich's console with prompt_toolkit's terminal management causes cursor conflicts. Rich is fine for CLI commands (`bae eval`) but not inside the interactive REPL. | prompt_toolkit's `print_formatted_text()` with ANSI or HTML formatting. |
| **logfire** | Pydantic's OTel backend. Adds cloud dependency. Cortex needs local in-process span capture, not external telemetry export. | `opentelemetry-sdk` with `InMemorySpanExporter` for local span access. Optional OTLP export for users who want it. |
| **opentelemetry-instrumentation-asyncio** | Auto-instruments asyncio primitives. Overkill -- cortex needs explicit, domain-meaningful spans ("graph_run", "node_fill", "nl_query"), not automatic instrumentation of every `gather()` and `create_task()`. | Manual `tracer.start_as_current_span()` at domain boundaries. |

---

## Deep Dive: prompt_toolkit for Async REPL

### Version: 3.0.52 (Aug 27, 2025)

**Confidence: HIGH** -- verified on [PyPI](https://pypi.org/project/prompt-toolkit/), [official docs](https://python-prompt-toolkit.readthedocs.io/en/stable/), and [GitHub](https://github.com/prompt-toolkit/python-prompt-toolkit)

**Requires-Python:** >=3.8 (verified via pip metadata)
**Dependencies:** `wcwidth` only

### Core Integration: PromptSession + asyncio

prompt_toolkit 3.0 uses asyncio natively. The key pattern for cortex:

```python
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout

async def cortex_loop():
    session = PromptSession("cortex> ")

    with patch_stdout():
        while True:
            try:
                text = await session.prompt_async()
                # dispatch to NL / Py / Graph mode handler
            except KeyboardInterrupt:
                continue
            except EOFError:
                break
```

**Critical detail:** `prompt_async()` yields control to the event loop while waiting for input. Background tasks (graph execution, AI inference) continue running. `patch_stdout()` ensures their output appears above the prompt line without corruption.

### Key APIs for Cortex

| API | Purpose in Cortex | Import Path |
|-----|-------------------|-------------|
| `PromptSession` | Persistent REPL session with history | `prompt_toolkit.PromptSession` |
| `prompt_async()` | Non-blocking input in asyncio loop | method on `PromptSession` |
| `patch_stdout()` | Concurrent output management | `prompt_toolkit.patch_stdout` |
| `KeyBindings` | Mode switching (Ctrl+N for NL, Ctrl+P for Py, etc.) | `prompt_toolkit.key_binding.KeyBindings` |
| `PygmentsLexer` | Python syntax highlighting in Py mode | `prompt_toolkit.lexers.PygmentsLexer` |
| `Completer` (ABC) | Custom completion per mode | `prompt_toolkit.completion.Completer` |
| `InMemoryHistory` / `FileHistory` | Session persistence | `prompt_toolkit.history` |
| `Application.create_background_task()` | Managed background coroutines | method on the underlying `Application` |
| `print_formatted_text()` | Styled output without Rich conflict | `prompt_toolkit.formatted_text` |

### Mode-Switching Architecture

prompt_toolkit supports conditional key bindings via `Filter`:

```python
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.filters import Condition

mode = "nl"  # or "py" or "graph"

bindings = KeyBindings()

@Condition
def is_nl_mode():
    return mode == "nl"

@bindings.add("c-p", filter=is_nl_mode)
def switch_to_py(event):
    nonlocal mode
    mode = "py"
    # swap lexer, completer, prompt string
```

The lexer, completer, and prompt string can all be dynamic callables on `PromptSession`, evaluated fresh each prompt cycle.

### Background Task Lifecycle

```python
# prompt_toolkit manages background tasks tied to the application
app = session.app
task = app.create_background_task(run_graph(graph, start_node, lm))
# Task is cancelled when the application exits
```

This integrates with cortex's channel-based I/O: graph execution writes to output channels, the REPL loop reads from them.

---

## Deep Dive: OpenTelemetry SDK for Spans

### Version: 1.39.1 (API and SDK aligned)

**Confidence: HIGH** -- verified via [pip metadata](https://pypi.org/project/opentelemetry-sdk/), [official instrumentation docs](https://opentelemetry.io/docs/languages/python/instrumentation/), and [SDK source](https://github.com/open-telemetry/opentelemetry-python)

**Requires-Python:** >=3.9
**Dependencies:** `opentelemetry-api`, `opentelemetry-semantic-conventions`, `typing-extensions` -- all already transitive deps of pydantic-ai

### Why Spans as Context Objects

Cortex uses OTel spans not primarily for telemetry export but as **structured context objects**. Each REPL interaction, graph run, node execution, and AI call gets a span. These spans form a tree that the reflective namespace can query:

```python
# In the cortex namespace, spans are accessible as context
ctx.spans          # all spans from current session
ctx.last_run       # spans from last graph execution
ctx.last_run.nodes # child spans for each node
```

### Setup Pattern for Cortex

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    SimpleSpanProcessor,
    InMemorySpanExporter,
)

# In-memory exporter for programmatic access
memory_exporter = InMemorySpanExporter()

provider = TracerProvider()
provider.add_span_processor(SimpleSpanProcessor(memory_exporter))
trace.set_tracer_provider(provider)

tracer = trace.get_tracer("bae.cortex")
```

**SimpleSpanProcessor** (not Batch) because cortex needs immediate access to finished spans. BatchSpanProcessor buffers with a 5-second default delay -- useless for interactive REPL feedback.

### Span Creation at Domain Boundaries

```python
# Graph execution span
with tracer.start_as_current_span("graph_run") as span:
    span.set_attribute("graph.start_node", start_node.__class__.__name__)
    result = await graph.arun(start_node, lm=lm)

# Node execution span (inside graph.arun)
with tracer.start_as_current_span("node_execute") as span:
    span.set_attribute("node.type", node_cls.__name__)
    span.set_attribute("node.routing", strategy[0])

# AI query span (NL mode)
with tracer.start_as_current_span("nl_query") as span:
    span.set_attribute("query.text", user_input)
    response = await agent.run(user_input)
```

### Async Context Propagation

OTel uses `contextvars` under the hood. In Python 3.14:
- `await` preserves contextvars (span context follows coroutine chains)
- `asyncio.create_task()` copies contextvars (child tasks inherit parent span)

This means spans nest correctly across `asyncio.gather()` calls in the resolver. No manual context threading needed.

### InMemorySpanExporter API

```python
# Get all finished spans as immutable tuple
spans = memory_exporter.get_finished_spans()

# Each span is a ReadableSpan with:
# .name           -> str ("graph_run", "node_execute", etc.)
# .context        -> SpanContext (trace_id, span_id)
# .parent         -> SpanContext | None (for nesting)
# .attributes     -> dict (custom key-value pairs)
# .events         -> list (timestamped log entries)
# .status         -> Status (OK, ERROR, UNSET)
# .start_time     -> int (nanosecond timestamp)
# .end_time       -> int (nanosecond timestamp)

# Clear between sessions
memory_exporter.clear()
```

### Integration with pydantic-ai

pydantic-ai already supports OTel via `Agent.instrument_all()`:

```python
from pydantic_ai import Agent

Agent.instrument_all()
# Now all agent.run() calls emit OTel spans automatically
# These appear as children of whatever span is active in cortex
```

This means LLM calls inside graph execution automatically nest under the graph_run span. Cortex gets visibility into token counts, model names, and latencies for free.

---

## Deep Dive: Channel-Based I/O (stdlib only)

### No External Library Needed

**Confidence: HIGH** -- verified Python 3.14 `asyncio.Queue.shutdown()` exists via runtime check

Python 3.13 added `Queue.shutdown(immediate=False)` and `QueueShutDown` exception. This is the missing feature that previously justified aiochannel. On Python 3.14, `asyncio.Queue` is a complete channel primitive.

### Labeled Channels Pattern

Cortex needs labeled I/O streams (stdout, stderr, ai_response, graph_trace, etc.). This is a thin wrapper:

```python
import asyncio

class ChannelBus:
    """Labeled async channels for multiplexed I/O."""

    def __init__(self):
        self._channels: dict[str, asyncio.Queue] = {}

    def channel(self, label: str) -> asyncio.Queue:
        if label not in self._channels:
            self._channels[label] = asyncio.Queue()
        return self._channels[label]

    async def put(self, label: str, item: object) -> None:
        await self.channel(label).put(item)

    async def get(self, label: str) -> object:
        return await self.channel(label).get()

    def shutdown(self, label: str | None = None) -> None:
        if label:
            self._channels[label].shutdown()
        else:
            for q in self._channels.values():
                q.shutdown()
```

This is ~20 lines. It does not warrant a dependency.

### Channel Consumers in the REPL

```python
async def render_output(bus: ChannelBus):
    """Background task: read from output channels, render to terminal."""
    while True:
        try:
            msg = await bus.get("display")
            print_formatted_text(msg)  # prompt_toolkit's output
        except asyncio.QueueShutDown:
            break
```

---

## Deep Dive: Reflective Namespace (stdlib only)

### No External Library Needed

**Confidence: HIGH** -- verified `annotationlib`, `inspect.get_annotations`, `typing.get_type_hints` all available on Python 3.14

### Python 3.14 Introspection Stack

| Tool | Purpose | Source |
|------|---------|--------|
| `typing.get_type_hints()` | Resolve type annotations (already used throughout bae) | `typing` stdlib |
| `annotationlib.get_annotations()` | Access annotations with deferred evaluation (PEP 649) | `annotationlib` stdlib (new in 3.14) |
| `annotationlib.Format.FORWARDREF` | Safely inspect unresolved forward refs | `annotationlib` stdlib |
| `inspect.signature()` | Function/method signatures | `inspect` stdlib |
| `inspect.getmembers()` | List object attributes by predicate | `inspect` stdlib |
| `inspect.iscoroutinefunction()` | Detect async callables (already used in resolver.py) | `inspect` stdlib |
| `type.__mro__` | Walk class hierarchy | builtin |
| `vars()` / `dir()` | Enumerate namespace contents | builtin |

### Reflective Namespace Design

The cortex namespace exposes bae objects with introspection:

```python
# In cortex, the user's namespace is a dict that auto-introspects
ns = CortexNamespace()
ns["graph"] = Graph(start=AnalyzeRequest)

# The namespace knows what graph is:
ns.describe("graph")
# -> Graph with 5 nodes: AnalyzeRequest -> Clarify | Process -> Review -> Done
# -> Start: AnalyzeRequest (3 plain fields, 1 dep field)

# Under the hood, this uses:
# - type(obj) for class detection
# - typing.get_type_hints() for field types
# - annotationlib.get_annotations(cls, format=Format.STRING) for display
# - inspect.signature() for callable signatures
# - graph._nodes for topology
```

### annotationlib for Display

The new `Format.STRING` mode is useful for the REPL -- it converts annotations back to source-like strings:

```python
import annotationlib

class MyNode(Node):
    query: str
    context: Annotated[Context, Dep(fetch_context)]
    history: Annotated[list[Message], Recall()]

# Get displayable annotations
anns = annotationlib.get_annotations(MyNode, format=annotationlib.Format.STRING)
# {'query': 'str', 'context': 'Annotated[Context, Dep(fetch_context)]', 'history': 'Annotated[list[Message], Recall()]'}
```

This gives the reflective namespace clean string representations without eval or repr hacks.

---

## Updated `pyproject.toml` Changes

```toml
[project]
name = "bae"
version = "0.4.0"
requires-python = ">=3.14"
dependencies = [
    "pydantic>=2.0",
    "pydantic-ai>=0.1",
    "dspy>=2.0",
    "typer>=0.12",
    # v4.0: cortex REPL
    "prompt-toolkit>=3.0.50",
    "opentelemetry-sdk>=1.39",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "ruff>=0.8",
    "pygments>=2.19",
]
```

**Why prompt-toolkit >=3.0.50:** The 3.0.x line is the stable async-native branch. 3.0.50+ includes Python 3.13/3.14 compatibility fixes. Floor at 3.0.50 rather than 3.0.52 to allow minor flexibility.

**Why opentelemetry-sdk >=1.39:** Matches the opentelemetry-api version already pulled in by pydantic-ai. The API and SDK versions are released in lockstep. >=1.39 ensures `InMemorySpanExporter.force_flush()` and other recent fixes.

**Why pygments in dev only:** Only needed for `PygmentsLexer(PythonLexer)` in the REPL's Py mode. Already a transitive dep of rich/typer in most environments, but explicit in dev ensures tests can verify syntax highlighting without relying on transitive resolution.

**What did NOT change:** `dspy>=2.0`, `pydantic>=2.0`, `pydantic-ai>=0.1`, `typer>=0.12` floors stay the same. No reason to bump them for cortex features.

---

## Dependency Weight Analysis

| Package | Install Size | Transitive Deps | Already Installed? |
|---------|-------------|------------------|--------------------|
| `prompt-toolkit` | ~1.5 MB | `wcwidth` (~50 KB) | No -- new |
| `opentelemetry-sdk` | ~400 KB | `opentelemetry-api` (already), `opentelemetry-semantic-conventions` (already), `typing-extensions` (already) | API yes, SDK no |
| `pygments` (dev) | ~8 MB | None | Yes (transitive via rich) |
| **Total new weight** | **~2 MB** | **1 new transitive dep (wcwidth)** | |

Minimal footprint. Two new runtime deps, one new transitive dep (`wcwidth`).

---

## Integration Points with Existing Bae Architecture

### asyncio Event Loop

Bae's existing async architecture (`Graph.arun()`, `resolve_fields()`, `asyncio.gather()` in resolver) runs inside an event loop. Cortex's prompt_toolkit REPL **also** runs inside an event loop via `prompt_async()`. These must share the same loop.

**Pattern:** Cortex owns the event loop. Graph execution is dispatched as a background task within the same loop:

```python
async def cortex_main():
    session = PromptSession()
    with patch_stdout():
        while True:
            text = await session.prompt_async()
            if is_graph_command(text):
                # Run graph in the same event loop, not blocking the prompt
                task = asyncio.create_task(graph.arun(start_node, lm=lm))
                # Results flow back via channels
```

### LM Protocol

The existing `LM` protocol (`make`, `decide`, `choose_type`, `fill`) is already async. It works unchanged inside cortex -- the LM calls happen inside `graph.arun()` which is an asyncio task.

For the AI agent object in the cortex namespace, pydantic-ai's `Agent` is also async-native. Its `.run()` method is a coroutine that fits naturally.

### OTel Span Nesting

Span hierarchy for a cortex session:

```
cortex_session                        # root span
  repl_turn (turn=1)                  # one prompt-response cycle
    nl_query                          # NL mode: AI interprets user intent
  repl_turn (turn=2)
    graph_run                         # Graph mode: execute a graph
      node_execute (AnalyzeRequest)   # per-node spans
        dep_resolve (fetch_context)   # dep resolution
        lm_fill                       # LLM call (auto-instrumented by pydantic-ai)
      node_execute (Process)
        lm_fill
      node_execute (Done)
  repl_turn (turn=3)
    py_exec                           # Py mode: exec() user code
```

The `InMemorySpanExporter` captures all of these. The reflective namespace can query them.

---

## Version Compatibility Matrix

| Component | Requires-Python | Latest | Bae Requires | Verified |
|-----------|----------------|--------|-------------|----------|
| Python | -- | 3.14.3 | >=3.14 | Runtime check |
| `prompt-toolkit` | >=3.8 | 3.0.52 | >=3.0.50 | [PyPI](https://pypi.org/project/prompt-toolkit/) |
| `opentelemetry-sdk` | >=3.9 | 1.39.1 | >=1.39 | [PyPI](https://pypi.org/project/opentelemetry-sdk/) |
| `opentelemetry-api` | >=3.9 | 1.39.1 | (transitive via pydantic-ai) | pip metadata |
| `pygments` | >=3.8 | 2.19.2 | >=2.19 (dev) | pip metadata |
| `wcwidth` | >=3.0 | (latest) | (transitive via prompt-toolkit) | pip metadata |
| `asyncio.Queue.shutdown` | >=3.13 | stdlib | >=3.14 (bae floor) | Runtime check: `True` |
| `annotationlib` | >=3.14 | stdlib | >=3.14 (bae floor) | Runtime check: available |

---

## Confidence Assessment

| Claim | Confidence | Verification |
|-------|------------|--------------|
| prompt_toolkit 3.0.52 is latest; `prompt_async()` is the async entry point | HIGH | [PyPI](https://pypi.org/project/prompt-toolkit/), [official docs](https://python-prompt-toolkit.readthedocs.io/en/stable/pages/advanced_topics/asyncio.html) |
| `patch_stdout()` prevents concurrent output corruption | HIGH | [Official asyncio example](https://github.com/prompt-toolkit/python-prompt-toolkit/blob/main/examples/prompts/asyncio-prompt.py), [docs](https://python-prompt-toolkit.readthedocs.io/en/stable/pages/asking_for_input.html) |
| `Application.create_background_task()` exists | HIGH | [API reference](https://python-prompt-toolkit.readthedocs.io/en/stable/pages/reference.html) |
| `KeyBindings` + `Condition` filter enables mode switching | HIGH | [Official docs](https://python-prompt-toolkit.readthedocs.io/en/stable/pages/asking_for_input.html) |
| OTel SDK 1.39.1 `InMemorySpanExporter.get_finished_spans()` returns `tuple[ReadableSpan, ...]` | HIGH | [SDK source](https://github.com/open-telemetry/opentelemetry-python/blob/main/opentelemetry-sdk/src/opentelemetry/sdk/trace/export/in_memory_span_exporter.py) |
| `SimpleSpanProcessor` passes spans immediately (no batching delay) | HIGH | [SDK export docs](https://opentelemetry-python.readthedocs.io/en/latest/sdk/trace.export.html) |
| `opentelemetry-api` is transitive dep of `pydantic-ai-slim` | HIGH | pip metadata: `pydantic-ai-slim` requires `opentelemetry-api>=1.28.0` |
| `Agent.instrument_all()` auto-instruments LLM calls with OTel | HIGH | [pydantic-ai docs](https://ai.pydantic.dev/logfire/), [DeepWiki](https://deepwiki.com/pydantic/pydantic-ai/4.2-instrumentation-and-monitoring) |
| `asyncio.Queue.shutdown()` available in Python 3.14 | HIGH | Runtime check on Python 3.14.3: `True` |
| `annotationlib` module available in Python 3.14 | HIGH | Runtime check: `Format` enum has VALUE, VALUE_WITH_FAKE_GLOBALS, FORWARDREF, STRING |
| `contextvars` propagation in asyncio (spans nest across tasks) | HIGH | [OTel async context example](https://github.com/open-telemetry/opentelemetry-python/blob/main/docs/examples/basic_context/async_context.py), [Python docs](https://docs.python.org/3/library/asyncio-task.html) |
| Rich output conflicts with prompt_toolkit terminal management | MEDIUM | Architectural inference from both libraries managing terminal state. prompt_toolkit's `print_formatted_text` is the safe alternative inside a running Application. |
| aiochannel is unnecessary given Queue.shutdown() | HIGH | [Python 3.13 Queue docs](https://docs.python.org/3.13/library/asyncio-queue.html), [aiochannel README](https://github.com/tudborg/aiochannel) -- feature parity now in stdlib |

---

## Sources

### Primary (HIGH confidence)

- [prompt_toolkit asyncio docs](https://python-prompt-toolkit.readthedocs.io/en/stable/pages/advanced_topics/asyncio.html) -- `run_async()`, `prompt_async()`, event loop integration
- [prompt_toolkit input docs](https://python-prompt-toolkit.readthedocs.io/en/stable/pages/asking_for_input.html) -- PromptSession, lexer, completer, key bindings, history, patch_stdout
- [prompt_toolkit API reference](https://python-prompt-toolkit.readthedocs.io/en/stable/pages/reference.html) -- Application.create_background_task, cancel_and_wait_for_background_tasks
- [prompt_toolkit REPL tutorial](https://python-prompt-toolkit.readthedocs.io/en/stable/pages/tutorials/repl.html) -- Complete REPL example with PygmentsLexer, WordCompleter, style
- [prompt_toolkit asyncio example](https://github.com/prompt-toolkit/python-prompt-toolkit/blob/main/examples/prompts/asyncio-prompt.py) -- PromptSession + patch_stdout + background task pattern
- [OTel Python instrumentation guide](https://opentelemetry.io/docs/languages/python/instrumentation/) -- TracerProvider setup, span creation, attributes, events, status, nesting
- [OTel InMemorySpanExporter source](https://github.com/open-telemetry/opentelemetry-python/blob/main/opentelemetry-sdk/src/opentelemetry/sdk/trace/export/in_memory_span_exporter.py) -- get_finished_spans, clear, shutdown, export
- [OTel async context example](https://github.com/open-telemetry/opentelemetry-python/blob/main/docs/examples/basic_context/async_context.py) -- Span propagation across async boundaries
- [Python 3.14 annotationlib docs](https://docs.python.org/3/library/annotationlib.html) -- Format enum, get_annotations(), ForwardRef, deferred evaluation
- [Python 3.14 asyncio.Queue docs](https://docs.python.org/3/library/asyncio-queue.html) -- Queue.shutdown(), QueueShutDown exception
- [pydantic-ai instrumentation docs](https://ai.pydantic.dev/logfire/) -- Agent.instrument_all(), InstrumentationSettings, OTel semantic conventions

### Secondary (MEDIUM confidence)

- [pydantic-ai OTel DeepWiki](https://deepwiki.com/pydantic/pydantic-ai/4.2-instrumentation-and-monitoring) -- Observability architecture, span names, event modes
- [OTel SDK export docs](https://opentelemetry-python.readthedocs.io/en/latest/sdk/trace.export.html) -- SimpleSpanProcessor vs BatchSpanProcessor
- [aiochannel GitHub](https://github.com/tudborg/aiochannel) -- Closable queue API, evaluated and decided against

### Previous Research (this project)

- v3.0 STACK.md (2026-02-08) -- DSPy eval/optimization, Rich, Copier, typer CLI (all still valid, not repeated here)
- v2.0 STACK.md (2026-02-07) -- DAG resolution, Annotated metadata, field categorization
- v1.0 codebase STACK.md (2026-02-04) -- Base stack analysis

---

*Stack research for v4.0 cortex REPL: 2026-02-13*
