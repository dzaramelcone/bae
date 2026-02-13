# Project Research Summary

**Project:** Bae v4.0 - Cortex REPL
**Domain:** Augmented async Python REPL for agent graph framework
**Researched:** 2026-02-13
**Confidence:** HIGH

## Executive Summary

Cortex is an interactive async Python REPL for bae that enables live development, debugging, and experimentation with agent graphs. Research shows that building this on prompt_toolkit 3.0 is the correct architectural choice -- it provides native asyncio support, async REPL primitives, and clean integration with bae's existing async foundation. The core insight is that cortex must own the event loop, not share or compete with it. Bae already has all the async infrastructure needed (Graph.arun(), async LM backends, asyncio.gather-based dep resolution); cortex adds an interactive shell layer that exposes these capabilities to users.

The recommended approach centers on four pillars: (1) A prompt_toolkit REPL shell with mode-based dispatch (NL/Py/Graph), (2) Channel-based I/O using labeled asyncio.Queue instances for multiplexed output, (3) A reflective namespace that exposes bae objects directly (no wrappers), and (4) Optional OTel instrumentation for observability. The stack additions are minimal -- only prompt_toolkit and opentelemetry-sdk as new runtime dependencies, leveraging Python 3.14's stdlib for everything else (asyncio.Queue.shutdown, annotationlib for introspection).

The critical risk is event loop ownership conflict. Bae's Graph.run() wraps arun() with asyncio.run(), which fails inside a running loop. Cortex must enforce that all graph execution uses await graph.arun(), never the sync wrapper. Secondary risks include output corruption from concurrent streams (solved by patch_stdout and channels), queue deadlocks (solved by unbounded output channels and multiplexed event waiting), and task lifecycle management (solved by TaskGroup or cortex-level cancellation). None of these are novel risks -- all have documented solutions in prompt_toolkit and asyncio patterns.

## Key Findings

### Recommended Stack

Research identified a lean stack with zero unnecessary dependencies. The decision to avoid IPython, aiochannel, typing-inspect, and other "obvious" choices is backed by analysis showing Python 3.14's stdlib now provides what those libraries once offered.

**Core technologies:**
- **prompt_toolkit >=3.0.50**: Async REPL foundation with native asyncio integration. PromptSession.prompt_async() runs on the same event loop as bae's graph execution. patch_stdout() prevents concurrent output corruption. KeyBindings and dynamic completers enable mode switching.
- **opentelemetry-sdk >=1.39**: Span instrumentation for REPL interactions, graph execution, and LM calls. InMemorySpanExporter enables programmatic span access for debugging. Already depends on opentelemetry-api (transitive via pydantic-ai), SDK adds TracerProvider and processors.
- **Python 3.14 stdlib**: asyncio.Queue.shutdown() replaces the need for aiochannel. annotationlib module (PEP 649/749) replaces typing-inspect. No external channel or introspection libraries needed.
- **pygments >=2.19 (dev only)**: Python syntax highlighting via prompt_toolkit's PygmentsLexer. Already transitive via rich/typer, made explicit for dev environments.

**Stack decisions validated:**
- Do NOT use IPython -- it owns the event loop and display system, making integration harder than building on prompt_toolkit directly
- Do NOT use aiochannel -- asyncio.Queue.shutdown() (Python 3.13+) provides closable queues
- Do NOT use rich inside the REPL -- prompt_toolkit and rich both manage terminal state, causing cursor conflicts
- Do NOT use nest_asyncio -- papers over event loop conflicts but introduces reentrancy bugs in bae's resolver

### Expected Features

Research identified three tiers of features based on REPL ecosystem analysis (ptpython, IPython, xonsh, Aider).

**Must have (table stakes):**
- Async Python execution with top-level await -- every modern Python REPL supports this; users expect await graph.arun() to work
- Syntax highlighting and multiline editing -- baseline expectation for 2026 REPLs
- Tab completion on namespace objects -- essential for discoverability
- Shared mutable namespace across modes -- variables set in Py mode visible in NL mode
- History persistence -- up-arrow recalls previous inputs
- Error display with full tracebacks -- including bae's typed exceptions with .trace attributes
- Graceful Ctrl-C / Ctrl-D -- cancellation without REPL exit, clean shutdown on exit
- Bae objects pre-loaded in namespace -- Node, Graph, Dep, Recall available without import
- Mode indicator in prompt -- user always knows which mode they're in

**Should have (differentiators):**
- Three-mode input (NL/Py/Graph) -- single REPL handles natural language, Python code, and graph commands without context switching
- Channel-based I/O with labeled streams -- all output tagged by source ([ai], [py], [graph], [otel]), users can mute/unmute channels
- AI as first-class namespace object -- ai("explain this") triggers NL interaction, ai.fill(Node) calls LM directly, composable like any Python object
- Reflective namespace introspection -- /ns shows all variables with types, /ns graph shows topology and fields
- Graph-aware REPL context -- last result in _, last trace in _trace, node instances directly inspectable
- OTel span instrumentation -- every command, graph execution, and LM call emits spans for observability

**Defer (v2+):**
- Ephemeral spawned interfaces (HitL) -- terminal/browser spawning for human-in-loop interactions has high complexity and tooling dependencies
- Full TUI layout -- scrollback terminal output sufficient, full-screen panes are scope creep
- Persistent AI conversation memory -- session-scoped is sufficient, cross-session memory requires storage layer
- Web-based REPL -- Jupyter already exists for that use case
- Voice/multimodal input -- adds audio capture complexity for unclear value

### Architecture Approach

The architecture is additive -- no existing bae modules require modification. Cortex is a new bae/repl/ package that imports from bae and shares its event loop. The only changes to existing code are adding repl exports to bae/__init__.py and a new CLI entry point in cli.py.

**Major components:**
1. **CortexShell (shell.py)** -- Owns the event loop and prompt session. Dispatches input to mode handlers (NL/Py/Graph) based on prefix detection. Uses prompt_toolkit's PromptSession.prompt_async() for non-blocking input. Implements mode switching via KeyBindings and dynamic completers.
2. **ChannelBus (channels.py)** -- Labeled message routing using asyncio.Queue. Each channel is a named stream (core.user.py.out, eng.graph.trace, ai.agent.action). Producers emit to channels, consumers subscribe to patterns. Terminal renderer reads from all unmuted channels and uses print_formatted_text() via patch_stdout.
3. **Namespace (namespace.py)** -- Builds the REPL's globals dict with bae objects (Node, Graph, LM backends) and session state (graph, trace, result, lm). No wrappers -- users interact with real bae objects. Reflective features leverage Pydantic's introspection (model_fields, model_json_schema) and Python's inspect module.
4. **AiAgent (ai.py)** -- Wraps the session's LM backend to provide NL-to-action translation. Thin layer -- just a single LM call with namespace context, not a complex reasoning chain. Emits output to ai.agent.action: channel.
5. **CortexContext (context.py)** -- Dataclass holding shared session state (namespace, lm, graph, trace, bus, tracer). Passed by reference, not a singleton, enabling testability.
6. **OTel spans (spans.py)** -- Wrapper instrumentation using TracedLM pattern (similar to existing TracingClaudeCLI in codebase). Creates spans at graph/node/LM-call granularity. Uses context managers (never manual start/end) for leak prevention.

**Integration pattern:** Cortex runs asyncio.run(shell.run()). Shell owns the event loop. Graph execution via await graph.arun() shares the loop. Background tasks (graph execution, output rendering) run concurrently with prompt_async(). No nested loops, no threading, pure cooperative async.

### Critical Pitfalls

Research identified 15 pitfalls across four categories. The top 5 that force architectural decisions:

1. **Event loop ownership conflict** -- Graph.run() calls asyncio.run() which fails inside a running loop. Prevention: cortex owns the loop, all graph execution uses await graph.arun(), never graph.run(). Detection: make graph.run() detect running loop and error clearly. Phase 1 critical.

2. **Output corruption from concurrent streams** -- Background graph execution prints to stdout, corrupting the prompt line. Prevention: all output through channels, use patch_stdout() around entire REPL session, print_formatted_text() for rendering. Phase 1 critical.

3. **Channel deadlock from bounded queue** -- If output queue is bounded and consumer is blocked waiting for user input, producers deadlock on full queue. Prevention: unbounded output queues (display output is finite per execution), multiplex prompt wait and output consumption with asyncio.wait(FIRST_COMPLETED). Phase 2 critical.

4. **asyncio.gather exception handling destroys sibling tasks** -- Resolver's gather() without return_exceptions=True orphans tasks on failure. In REPL, this leaks LLM subprocesses and running tasks across interactions. Prevention: use TaskGroup (Python 3.11+) or cortex-level task management with cancellation. Phase 1 high priority.

5. **OTel context propagation breaks across gather boundaries** -- Span context copied at task creation, not shared. Span leaks from unclosed spans in failed deps. Prevention: span at right granularity (graph/node/LM, not individual deps), always use context managers, test trace hierarchy. Phase 4 high priority.

**Common theme:** All critical pitfalls relate to async event loop management. Cortex inverts bae's execution model from batch (script controls loop lifecycle) to interactive (REPL controls loop, graph execution is a guest). Getting this right in Phase 1 is non-negotiable.

## Implications for Roadmap

Based on dependency analysis and pitfall avoidance, four phases are recommended:

### Phase 1: REPL Shell Foundation
**Rationale:** Everything depends on having a working event loop and prompt session. Validates that prompt_toolkit + asyncio + bae's async foundation work together. Must establish event loop sovereignty before building on it.

**Delivers:** Working async Python REPL with bae objects in namespace. Users can await graph.arun(node, lm=lm) interactively. Single mode (Python exec) with history persistence and error handling.

**Addresses:** Table stakes features (async exec, syntax highlighting, tab completion, shared namespace, history, error display, Ctrl-C/Ctrl-D)

**Avoids:** Pitfall #1 (event loop conflict) by establishing cortex as loop owner. Pitfall #2 (output corruption) by setting up patch_stdout. Pitfall #4 (task leaks) by defining task lifecycle. Pitfall #10 (graceful shutdown) by implementing shutdown sequence. Pitfall #12 (user code crashes) by exception boundary.

**Components:** CortexContext, namespace builder, CortexShell (basic), CLI entry point

**Research flag:** Standard patterns (prompt_toolkit async REPL is well-documented). No additional research needed.

### Phase 2: Channel I/O and Mode Dispatch
**Rationale:** Channels are the I/O backbone for all modes. Mode detection needs channels for output routing. AI agent (Phase 3) needs channels to emit responses. Must exist before multi-mode functionality.

**Delivers:** Labeled output streams with mute/unmute controls. Mode detection (NL/Py/Graph) with prefix-based dispatch. All output routed through channels, terminal renderer consumes from all unmuted channels.

**Addresses:** Differentiator features (channel I/O, mode switching, channel surfing). Namespace introspection (/ns command showing variables and types).

**Avoids:** Pitfall #3 (channel deadlock) by unbounded queues and multiplexed waiting. Pitfall #6 (namespace GC issues) by history depth limits. Pitfall #9 (namespace leaks internals) by read-only views. Pitfall #13 (expensive tab completion) by ThreadedCompleter and caching.

**Uses:** asyncio.Queue (stdlib), ChannelBus pattern from research

**Implements:** ChannelBus component, mode dispatcher in shell, reflective namespace features

**Research flag:** Channel architecture is novel (no existing Python REPL does this). Consider targeted research on pub/sub patterns and asyncio.Queue multiplexing if implementation complexity exceeds estimates.

### Phase 3: AI Agent Integration
**Rationale:** Requires both namespace (Phase 1) and channels (Phase 2) to function. AI output goes to [ai] channel, AI reads namespace for context. Can't build AI before its infrastructure exists.

**Delivers:** AI as callable object in namespace. ai("explain graph") for NL interaction, ai.fill(Node) for direct LM access. Context assembly from namespace state. Output on [ai] channel.

**Addresses:** Differentiator feature (AI as first-class object). NL mode dispatch.

**Avoids:** Pitfall #7 (AI context explosion) by scoped context and summaries. Pitfall #8 (streaming conflicts) by dedicated output region or gated input.

**Uses:** Existing bae LM backends, wraps session's lm object

**Implements:** AiAgent component, NL mode handler

**Research flag:** AI context scoping and summarization patterns may need research if naive approach (full namespace serialization) hits token limits in practice. Consider research-phase if MVP testing shows context issues.

### Phase 4: OTel Instrumentation
**Rationale:** Observability over working code. Requires all components to be functional. OTel is optional -- cortex works without it. Can be added incrementally without changing existing code.

**Delivers:** Span instrumentation for REPL commands, graph execution, node steps, LM calls. [otel] channel for human-readable span output. Optional OTLP exporter for external collectors.

**Addresses:** Differentiator feature (OTel spans for observability)

**Avoids:** Pitfall #5 (context propagation) by correct span granularity and context managers. Pitfall #11 (performance overhead) by spans at right level, events not spans for deps, sampling.

**Uses:** opentelemetry-sdk, InMemorySpanExporter, TracerProvider

**Implements:** OTel spans component, TracedLM wrapper, span decorators

**Research flag:** Standard patterns (OTel Python instrumentation is well-documented). Span hierarchy testing may need attention to validate no orphan spans in complex gather scenarios.

### Phase Ordering Rationale

- **Sequential dependency chain:** Phase 1 establishes the event loop foundation that Phases 2-4 build on. Phase 2's channels are required by Phase 3's AI output and Phase 4's OTel events. Phase 3 is independent of Phase 4 (AI doesn't need OTel).
- **Pitfall mitigation:** All critical pitfalls are addressed in Phases 1-2. By the time AI and OTel are added, the async architecture is proven stable.
- **Incremental value:** Each phase delivers a usable REPL. Phase 1 = basic async Python REPL. Phase 2 = multi-mode REPL with channels. Phase 3 = AI-augmented REPL. Phase 4 = observable REPL.
- **Risk front-loading:** The highest-risk components (event loop management, channel architecture) are in Phases 1-2. Phases 3-4 are lower risk because they consume stable infrastructure.

### Research Flags

**Phases needing deeper research during planning:**
- **Phase 2:** Channel multiplexing architecture is novel. If complexity exceeds estimates or deadlock scenarios emerge during implementation, consider targeted research on asyncio pub/sub patterns and bounded queue strategies.
- **Phase 3:** AI context assembly and token budgeting may need research if MVP shows context explosion. Summarization strategies and sliding window patterns documented but not proven at bae's scale.

**Phases with standard patterns (skip research-phase):**
- **Phase 1:** Async REPL on prompt_toolkit is well-documented with canonical examples. Event loop patterns in asyncio are Python fundamentals.
- **Phase 4:** OTel Python instrumentation has extensive official docs. TracedLM wrapper follows existing codebase pattern (TracingClaudeCLI).

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | prompt_toolkit 3.0.52 and opentelemetry-sdk 1.39+ verified via PyPI, docs, and source inspection. Python 3.14 stdlib features (Queue.shutdown, annotationlib) confirmed via runtime checks. All "do NOT add" decisions backed by analysis showing stdlib provides equivalents. |
| Features | HIGH | Table stakes derived from REPL ecosystem analysis (ptpython, IPython, xonsh) with consistent patterns. Differentiators validated against existing tools (Aider, Claude Code, Open Interpreter) showing novelty. Anti-features based on architectural complexity and YAGNI principle. |
| Architecture | HIGH | Integration points mapped from direct codebase analysis (graph.py, resolver.py, lm.py). Event loop sharing pattern verified via official prompt_toolkit asyncio examples. Channel architecture inferred from Docker Compose and asyncio.Queue docs. No modifications to core bae modules needed. |
| Pitfalls | HIGH | Event loop conflicts and output corruption verified via prompt_toolkit issues and asyncio docs. Task lifecycle and gather() semantics from Python stdlib docs and CPython issues. OTel context propagation from official examples. All critical pitfalls have documented solutions. |

**Overall confidence:** HIGH

Research converged on consistent recommendations from multiple high-quality sources. Stack choices are backed by official documentation and runtime verification. Architecture patterns have canonical examples in prompt_toolkit and ptpython. Pitfalls are known issues with established solutions.

### Gaps to Address

**Medium priority (validate during implementation):**
- Channel multiplexing scalability: Research shows patterns for pub/sub and asyncio.Queue, but the specific design (labeled queues with wildcard subscription) is novel. If >10 concurrent channels cause latency issues, may need buffering or backpressure strategies beyond unbounded queues.
- AI context token budgeting: Scoped context and summarization are documented strategies, but bae's specific context (graph topology, trace history, Pydantic models) may have unique characteristics. Monitor token counts in Phase 3 MVP and adjust summarization aggressiveness.

**Low priority (defer until needed):**
- Ephemeral spawned interfaces: Ghostty's programmatic API is evolving (GitHub discussion #2353). Inline HitL prompts are sufficient for v4.0. Terminal spawning deferred to v5.0 when Ghostty scripting stabilizes.
- Persistent conversation memory: In-session AI context is sufficient for v4.0. Cross-session memory requires storage layer and raises UX questions (what gets persisted? how long?). Defer until user feedback shows need.

## Sources

### Primary (HIGH confidence)
- [prompt_toolkit official docs](https://python-prompt-toolkit.readthedocs.io/) -- asyncio integration, PromptSession API, patch_stdout, completers, key bindings
- [ptpython async embed example](https://github.com/prompt-toolkit/ptpython/blob/main/examples/asyncio-python-embed.py) -- canonical async REPL pattern with custom namespace
- [prompt_toolkit asyncio-prompt.py](https://github.com/prompt-toolkit/python-prompt-toolkit/blob/main/examples/prompts/asyncio-prompt.py) -- background tasks with patch_stdout
- [Python asyncio docs](https://docs.python.org/3/library/asyncio-task.html) -- TaskGroup, gather semantics, cancellation
- [Python asyncio.Queue docs](https://docs.python.org/3/library/asyncio-queue.html) -- shutdown() method (3.13+)
- [OpenTelemetry Python instrumentation](https://opentelemetry.io/docs/languages/python/instrumentation/) -- TracerProvider, span creation, context propagation
- [OTel async context example](https://github.com/open-telemetry/opentelemetry-python/blob/main/docs/examples/basic_context/async_context.py) -- contextvars propagation in asyncio
- [Python 3.14 annotationlib](https://docs.python.org/3/library/annotationlib.html) -- PEP 649/749, Format enum, get_annotations
- [pydantic-ai instrumentation](https://ai.pydantic.dev/logfire/) -- Agent.instrument_all() for OTel spans
- Bae codebase analysis (graph.py, resolver.py, lm.py, node.py) -- integration points verified

### Secondary (MEDIUM confidence)
- [Docker multiplexed logs](https://docs.docker.com/reference/cli/docker/container/logs/) -- labeled stream pattern for channel architecture
- [OTel GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/) -- span naming for AI operations (Development status)
- [Anthropic context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) -- context scoping, history management
- [Armin Ronacher async pressure](https://lucumr.pocoo.org/2020/1/1/async-pressure/) -- backpressure patterns in asyncio
- [OneUptime OTel performance](https://oneuptime.com/blog/post/2026-01-07-opentelemetry-performance-impact/view) -- span overhead and sampling
- [Ghostty scripting discussion](https://github.com/ghostty-org/ghostty/discussions/2353) -- programmatic API status (evolving)

### Tertiary (LOW confidence)
- xonsh, Aider, Open Interpreter comparisons -- mode switching patterns inferred from documentation and demos, not direct usage
- Channel deadlock scenarios -- extrapolated from general asyncio bounded-buffer patterns, not tested in bae context
- OTel span overhead quantification (5ms estimate) -- derived from benchmarks in unrelated projects, not measured in bae

---
*Research completed: 2026-02-13*
*Ready for roadmap: yes*
