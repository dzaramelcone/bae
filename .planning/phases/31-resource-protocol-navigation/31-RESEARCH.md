# Phase 31: Resource Protocol + Navigation - Research

**Researched:** 2026-02-16
**Domain:** Resourcespace protocol, registry, navigation state, tool dispatch routing, output pruning
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Resource entry display
- Functions table columns: system tool override (if applicable) -> function name -> one-line procedural description
- Docstrings are result-oriented: describe what the agent gets back, not what the function does
- Python hints for advanced `<run>` operations in a separate "Advanced:" block after the functions table
- Entry always includes resource state (e.g., current path, item count) -- agent immediately knows where it is
- Entry includes breadcrumb showing parent chain (e.g., "home > source > meta")

#### Navigation feel
- `.nav()` shows an indented tree view of the full navigable structure from current position
- Tree marks the agent's current position with a "you are here" indicator
- Tree depth capped at 2-3 levels; collapsed nodes show "+N more" to stay within token budget
- Tree updates on next `nav()` call, not automatically when registry changes
- `@resource()` mentions are navigable anywhere they appear -- tool results, errors, nav listings
- Navigation supports both stack-based `back()` and explicit direct jumps
- Direct jump to any target including nested (e.g., `source.meta()` from anywhere, not just from `source()`)
- Brief transition message on navigation (e.g., "Left source -> entering tasks")
- `homespace()` returns to root, shows root nav tree (no dashboard -- that's Phase 36)

#### Error messaging
- Protocol wraps all resource errors into a consistent format -- uniform experience across resources
- Human-readable messages only, no error codes -- the consumer is an AI
- Unsupported tool: fact + nav hint pointing to the right resource (e.g., "source does not support edit. Try @source.meta()")
- Bad navigation: error + closest match fuzzy correction (e.g., "No resource 'sourc'. Did you mean @source()?")
- Errors always include @resource() hyperlinks when a better resource exists for the operation
- Tools at homespace root auto-dispatch to sensible defaults (e.g., `read()` at root lists resourcespaces)
- Multiple errors in a single operation: collect all and report together, not fail-fast
- Errors subject to the same 500 token cap as all other output

#### Pruning
- 500 token hard cap -- protocol-level constant, not configurable per-resource
- Structure-first preservation: keep headings, counts, shape; trim content details
- Protocol layer handles all pruning -- generic, not resource-specific
- Deterministic algorithm: no LM calls, algorithmic truncation with structure preservation
- Always indicate when pruning happened (e.g., "[pruned: 42 -> 10 items]") so agent knows more exists

### Claude's Discretion
- Whether to mark unvisited vs visited targets in the nav tree
- Exact breadcrumb formatting
- Specific tree indentation and collapse thresholds
- Pruning algorithm internals (which items to keep, how to count structure tokens)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope

</user_constraints>

## Summary

Phase 31 builds the foundational resource protocol that all subsequent v7.0 phases compose on. The AI agent will navigate a self-describing resource tree where calling a resource as a function enters it, `.nav()` shows an indented tree view, and standard tools (read/write/edit/glob/grep) dispatch to the current resource's handlers. This phase delivers the protocol, registry, navigation state machine, tool dispatch routing, output pruning, and error formatting -- but NOT any concrete resourcespaces (those are Phases 32-35).

The implementation maps entirely to existing codebase patterns: Protocol+Registry (from `ChannelRouter`/`Channel` in `channels.py`), navigation state in `ContextVar` (from `_graph_ctx` in `engine.py`), tool dispatch interception (wrapping existing `_exec_*` functions from `ai.py`), and tag-based tool invocation (extending the existing `_TOOL_TAG_RE` regex system). Zero new dependencies.

The key insight from the CONTEXT.md decisions is that navigation is function-call-based (`source()`, `source.meta()`, `homespace()`), not tag-based (`<nav:target>`). Resources are callable objects in the namespace, and `@resource()` mentions anywhere in output serve as navigable hyperlinks. This differs from the earlier research architecture (which assumed `<nav:>` tags) and must be reflected in the implementation.

**Primary recommendation:** Build the Resourcespace Protocol and ResourceRegistry as new modules in `bae/repl/`, modify `ai.py`'s `run_tool_calls()` to dispatch through a ToolRouter, and inject current resource location into every AI context preamble. Navigation is callable-based (namespace functions), not tag-based.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `typing.Protocol` | stdlib 3.14 | Resourcespace interface | Same pattern as `ViewFormatter` protocol in `channels.py`. Runtime-checkable for registration validation. |
| `dict[str, Resourcespace]` | stdlib | Flat resourcespace registry | O(1) lookup by name. Same pattern as `ChannelRouter._channels`. |
| `contextvars.ContextVar` | stdlib 3.14 | Navigation state (current location + stack) | Async-safe, proven in `engine.py`'s `_graph_ctx`. |
| `dataclasses` | stdlib 3.14 | Internal structs (NavigationState, ResourceError) | Lightweight data carriers without Pydantic overhead. |
| `difflib.get_close_matches` | stdlib | Fuzzy matching for navigation error correction | "Did you mean @source()?" from mistyped resource names. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `re` | stdlib | Extended tool tag regex for resource function calls | Parsing `@resource()` mentions in AI output for navigation dispatch |
| `textwrap` | stdlib | Token-aware output wrapping and truncation | Pruning algorithm internals |
| `rich.tree.Tree` | 14.3.2 | Nav tree rendering | `.nav()` indented tree display with "you are here" marker |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Flat dict registry | `anytree` / `treelib` | External dependency for a 3-4 level tree. Path-prefix matching on flat dict is simpler. |
| ContextVar for nav state | Thread-local | Cortex is async. Thread-locals don't propagate across await. ContextVars do. |
| `difflib` fuzzy matching | `rapidfuzz` / `thefuzz` | External dependency for <20 items to match against. `difflib.get_close_matches` is sufficient. |
| `rich.tree.Tree` for nav | Plain text indentation | Rich Tree provides clean connecting lines and collapse. Already a dependency. |

**Installation:** No changes to `pyproject.toml`.

## Architecture Patterns

### Recommended Project Structure
```
bae/repl/
    resource.py          # Resourcespace protocol, ResourceRegistry, NavigationState, error formatting
    tools.py             # ToolRouter -- intercepts tool calls, dispatches by location, pruning
    ai.py                # MODIFIED: run_tool_calls gains router, _build_context gains location
    shell.py             # MODIFIED: creates registry + router, passes to AI, toolbar widget
    ai_prompt.md         # MODIFIED: navigation instructions appended
    toolbar.py           # MODIFIED: location widget added
```

### Pattern 1: Resourcespace Protocol
**What:** A `typing.Protocol` defining the interface every resourcespace must implement. Follows the exact same shape as `ViewFormatter` in `channels.py`.
**When to use:** Every resourcespace (source, tasks, memory, search) implements this protocol.
**Source:** Existing pattern in `bae/repl/channels.py` lines 43-61

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class Resourcespace(Protocol):
    """A navigable domain that responds to standard tool verbs."""
    name: str
    description: str

    def enter(self) -> str:
        """Entry display: functions table, state, breadcrumb, Python hints."""
        ...

    def nav(self) -> str:
        """Indented tree view of navigable structure from current position."""
        ...

    def read(self, resource_id: str = "") -> str:
        """Read a resource. Returns content string."""
        ...

    def supported_tools(self) -> set[str]:
        """Which standard tools this resource supports."""
        ...

    def children(self) -> dict[str, "Resourcespace"]:
        """Subresourcespaces (for dotted navigation like source.meta())."""
        ...
```

Not all methods need implementation per resourcespace. Unsupported tools raise `ResourceError` -- the protocol layer catches and formats.

### Pattern 2: ResourceRegistry + Navigation State Machine
**What:** Flat dict of resourcespaces with a navigation stack. The agent calls `source()` to navigate in, `back()` to pop, `homespace()` to reset. Direct jumps via `source.meta()` push multiple levels at once.
**When to use:** Singleton on CortexShell, passed to AI and ToolRouter.
**Source:** Analogous to `GraphRegistry` in `engine.py` and `ChannelRouter` in `channels.py`

```python
class ResourceRegistry:
    def __init__(self):
        self._spaces: dict[str, Resourcespace] = {}
        self._stack: list[Resourcespace] = []  # navigation history

    @property
    def current(self) -> Resourcespace | None:
        return self._stack[-1] if self._stack else None

    def navigate(self, target: str) -> str:
        """Navigate to target. Supports dotted paths (source.meta).
        Returns entry display of the target resource."""
        ...

    def back(self) -> str:
        """Pop navigation stack. Returns entry display of parent."""
        ...

    def homespace(self) -> str:
        """Clear stack, return to root. Returns root nav tree."""
        ...

    def breadcrumb(self) -> str:
        """Parent chain string: home > source > meta"""
        ...
```

### Pattern 3: ToolRouter Dispatch
**What:** Intercepts tool calls from `run_tool_calls()`, checks current resource, dispatches to resource-specific handler or homespace (filesystem) fallback. Applies 500-token pruning on all resource output (but not errors).
**When to use:** Every tool call flows through ToolRouter.
**Source:** Wraps existing `_exec_*` functions from `ai.py` lines 271-345

```python
TOKEN_CAP = 500  # protocol-level constant
CHAR_CAP = TOKEN_CAP * 4  # ~4 chars/token heuristic

class ToolRouter:
    def __init__(self, registry: ResourceRegistry):
        self._registry = registry

    def dispatch(self, tool: str, arg: str, **kwargs) -> str:
        """Route tool call to current resource or homespace."""
        rs = self._registry.current
        if rs is None:
            return self._homespace_dispatch(tool, arg, **kwargs)
        if tool not in rs.supported_tools():
            return format_unsupported_error(rs, tool)
        try:
            result = getattr(rs, tool)(arg, **kwargs)
            return self._prune(result)
        except ResourceError as e:
            return str(e)  # errors never pruned

    def _prune(self, output: str) -> str:
        """Structure-first pruning to 500 token cap."""
        ...
```

### Pattern 4: Callable Navigation Objects in Namespace
**What:** Resources are exposed as callable objects in the REPL namespace. `source()` navigates into source resourcespace and returns the entry display. `source.meta()` navigates into the meta subresource. `homespace()` returns to root. These are Python callables, not `<nav:>` tags.
**When to use:** This is how the AI invokes navigation -- through `<run>source()</run>` blocks.
**Source:** Decision from CONTEXT.md; follows same pattern as `ns()` in namespace.py

```python
class ResourceHandle:
    """Callable namespace object that navigates on call."""
    def __init__(self, name: str, registry: ResourceRegistry):
        self._name = name
        self._registry = registry

    def __call__(self) -> str:
        return self._registry.navigate(self._name)

    def __getattr__(self, child: str):
        """Enable dotted access: source.meta()"""
        return ResourceHandle(f"{self._name}.{child}", self._registry)

    def __repr__(self):
        return f"@{self._name}() -- navigate to {self._name}"
```

### Pattern 5: Structure-First Pruning Algorithm
**What:** Deterministic algorithm that preserves structure (headings, counts, shape) while trimming content details. Never prunes error output. Always indicates when pruning happened.
**When to use:** Protocol layer applies to all resourcespace output.
**Source:** Decision from CONTEXT.md

```
Algorithm:
1. Measure output length against CHAR_CAP (~2000 chars for 500 tokens)
2. If under cap: return as-is
3. Parse into structural blocks (headings, list items, table rows)
4. Keep all headings and structural markers
5. Preserve first N items from each block until budget exhausted
6. Append "[pruned: {total} -> {shown} items]"
7. Never prune lines matching error patterns
```

### Anti-Patterns to Avoid
- **New tool tags for navigation:** `<nav:target>` was the earlier research proposal. Dzara's decisions use callable functions instead (`source()`, `homespace()`). Do NOT add `<nav:>` tags.
- **Resource-specific tool verbs:** Do NOT create `source_read`, `task_search` etc. Same 5 tools (R/W/E/G/Grep), different behavior per resource context.
- **Eager resource loading:** Do NOT load all resource content when entering. Entry display is a summary; the agent uses tools to explore.
- **Persistent navigation across sessions:** Always start at homespace. The AI re-navigates per conversation.
- **Configurable per-resource token cap:** The cap is 500 tokens, period. Protocol-level constant.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Fuzzy name matching | Custom Levenshtein | `difflib.get_close_matches` | Stdlib, handles the <20 item matching perfectly |
| Tree rendering | Custom indentation logic | `rich.tree.Tree` | Already a dependency, handles connecting lines and collapse |
| Token counting | Custom tokenizer | `len(text) // 4` heuristic | No tokenizer available without new dep; 4 chars/token is standard heuristic for English text |
| Error formatting | Per-resource error logic | Protocol-level `ResourceError` class | Uniform formatting across all resources per CONTEXT.md decision |
| Navigation state | Custom state tracking | `list` as stack + ContextVar | Async-safe, simple push/pop, proven pattern in engine.py |

**Key insight:** This phase is entirely composition of existing patterns. No novel algorithms needed. The pruning algorithm is the only non-trivial new logic, and it's deterministic string manipulation.

## Common Pitfalls

### Pitfall 1: Navigation State Desync
**What goes wrong:** AI navigates to a resource, but its context drifts or gets pruned. AI acts on resource A while believing it's at B.
**Why it happens:** `_build_context()` currently only runs on first prompt (line 106-108 of ai.py). Subsequent eval loop turns don't include location state.
**How to avoid:** Inject current resource location into EVERY `_send()` call, not just first `_build_context()`. Tool outputs must echo the resource context they operated in (e.g., `[source] read ai.py (42 lines)`).
**Warning signs:** AI references a resource path inconsistent with the actual navigation stack.

### Pitfall 2: Tool Scoping Leak
**What goes wrong:** Operations escape resource boundary via absolute paths, `../` traversal, or home-relative paths.
**Why it happens:** Existing `_exec_*` functions take raw paths with no validation (ai.py lines 271-345).
**How to avoid:** Tool scoping happens at ToolRouter dispatch layer, BEFORE calling resource methods. Resources never see unscoped paths. ToolRouter validates that paths stay within resource boundaries.
**Warning signs:** AI reads/writes files outside the current resource's scope.

### Pitfall 3: Entry Display Token Bloat
**What goes wrong:** The functions table + breadcrumb + state + Python hints exceed the 500-token cap, consuming too much context on every navigation.
**Why it happens:** Each resource has 5-10 functions, each with a docstring. State lines, breadcrumb, and Python hints add up.
**How to avoid:** Entry displays must be tightly budgeted. Functions table uses single-line descriptions (per CONTEXT.md: "one-line procedural description"). Python hints go in a separate "Advanced:" block that can be pruned first. Measure entry display length during testing and enforce a budget (~300 tokens for entry, leaving 200 for state/breadcrumb).
**Warning signs:** Entry display consistently exceeds 1200 characters (~300 tokens).

### Pitfall 4: `@resource()` Parsing Conflicts
**What goes wrong:** `@resource()` mentions in AI output collide with Python decorators, email addresses, or other `@` prefixed text in tool output content.
**Why it happens:** `@` is overloaded in Python (decorators, matmul operator) and common in prose (email, social handles).
**How to avoid:** `@resource()` pattern must match only against known registered resource names. The regex should be anchored to `@<known_name>()` with the parentheses required as disambiguation. Never match bare `@word` without trailing `()`.
**Warning signs:** False positive navigation triggers from code samples in tool output.

### Pitfall 5: Pruning Destroys Structure
**What goes wrong:** Naive character truncation cuts a heading in half, breaks a table mid-row, or splits a path at an inconvenient boundary.
**Why it happens:** Simple `text[:CHAR_CAP]` doesn't understand content structure.
**How to avoid:** Parse output into lines/blocks before pruning. Truncate at block boundaries, not character boundaries. Always preserve the first block (usually a heading or summary) and the last block (often contains a count or navigation hint).
**Warning signs:** Pruned output has dangling table formatting, broken paths, or headings without content.

### Pitfall 6: Circular Navigation via Dotted Paths
**What goes wrong:** `source.meta.source.meta.source...` creates an infinite depth illusion, or `back()` after a deep direct jump returns to an unexpected location.
**Why it happens:** Dotted navigation (`source.meta()`) is a direct jump, not iterative descent. The stack grows without bound if jumps accumulate.
**How to avoid:** Dotted navigation resolves to the target directly and pushes only the final resource onto the stack (not each intermediate). `back()` always returns to wherever the agent was before the jump. Cap stack depth at a reasonable limit (10-20).
**Warning signs:** Stack depth exceeds 5-6 during normal operation.

## Code Examples

Verified patterns from the existing codebase:

### Creating a Protocol + Registry (from channels.py)
```python
# Source: bae/repl/channels.py lines 43-61, 132-171
@runtime_checkable
class ViewFormatter(Protocol):
    def render(self, channel_name: str, color: str, content: str, *, metadata: dict | None = None) -> None: ...

@dataclass
class ChannelRouter:
    _channels: dict[str, Channel] = field(default_factory=dict, repr=False)

    def register(self, name: str, color: str, ...) -> Channel:
        ch = Channel(name=name, color=color, ...)
        self._channels[name] = ch
        return ch

    def write(self, channel: str, content: str, **kwargs) -> None:
        ch = self._channels.get(channel)
        if ch:
            ch.write(content, **kwargs)
```

### Tool Dispatch Through Registry (from ai.py)
```python
# Source: bae/repl/ai.py lines 356-361, 393-456
_TOOL_EXEC = {
    "R": _exec_read,
    "E": _exec_edit_read,
    "G": _exec_glob,
    "Grep": _exec_grep,
}

def run_tool_calls(text: str) -> list[tuple[str, str]]:
    # Strip executable blocks, scan for tags, dispatch
    prose = _EXEC_BLOCK_RE.sub("", text)
    for m in _TOOL_TAG_RE.finditer(prose):
        tool = _TOOL_NAMES.get(m.group(1).lower())
        fn = _TOOL_EXEC.get(tool)
        if fn:
            pending.append((m.start(), tag, lambda f=fn, a=m.group(2): f(a)))
```

### ContextVar for Async State (from engine.py)
```python
# Source: bae/repl/engine.py lines 21-23
_graph_ctx: contextvars.ContextVar[tuple | None] = contextvars.ContextVar(
    "_graph_ctx", default=None
)
# Set in shell.py __init__:
_graph_ctx.set((self.engine, self.tm, self._lm, _notify))
```

### Namespace Callable Object (from namespace.py)
```python
# Source: bae/repl/namespace.py lines 60-85
class NsInspector:
    def __init__(self, namespace: dict) -> None:
        self._ns = namespace

    def __call__(self, obj=None):
        if obj is None:
            self._list_all()
        elif isinstance(obj, Graph):
            self._inspect_graph(obj)
        # ...

    def __repr__(self):
        return "ns() -- inspect namespace. ns(obj) -- inspect object."
```

### Seeding Namespace with Callables (from shell.py)
```python
# Source: bae/repl/shell.py lines 207-239
class CortexShell:
    def __init__(self) -> None:
        self.namespace: dict = seed()
        # ... add objects to namespace ...
        self.namespace["store"] = self.store
        self.namespace["channels"] = self.router
        self.namespace["ai"] = self.ai
        self.namespace["engine"] = self.engine
```

### Rich Tree Rendering (from rich docs)
```python
from rich.tree import Tree
from bae.repl.views import _rich_to_ansi

tree = Tree("[bold]home[/bold]")
source = tree.add("@source()")
source.add("@source.meta()")
tasks = tree.add("@tasks()")
tree.add("@memory()")

ansi_str = _rich_to_ansi(tree)  # uses existing pipeline from views.py
```

### Entry Display Format (from CONTEXT.md decisions)
```
home > source
source -- bae project source tree (34 .py files)

| Tool     | Function    | Returns                                    |
|----------|-------------|---------------------------------------------|
| read     | read(path)  | File content with line numbers              |
| write    | write(path) | Confirmation with byte count                |
| edit     | edit(path)  | Updated file content at changed region      |
| glob     | glob(pat)   | Matching paths with file sizes              |
| grep     | grep(pat)   | Matching lines with file:line:content       |

Advanced:
  <run>source.files()</run>  -- list all tracked files as Python list
  <run>source.tree()</run>   -- full directory tree as string
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `<nav:target>` tag in AI output | `source()` callable in namespace | CONTEXT.md discussion | Navigation is Python function calls, not tool tags |
| Flat namespace dump in context | Resource-scoped context with breadcrumb | v7.0 architecture decision | AI sees only current resource's tools, not everything |
| 4000 char tool output cap | 500 token cap with structure-first pruning | v7.0 requirements RSP-09 | 5x reduction, but smarter truncation |
| All errors treated same as output | Errors never pruned (RSP-10) | v7.0 requirements | AI learns from failures across pruning cycles |

**Deprecated/outdated:**
- `<nav:target>` tags from earlier research architecture -- replaced by callable navigation objects
- Raw `_exec_*` functions from ai.py as sole tool dispatch -- now wrapped by ToolRouter
- `_build_context()` as flat namespace dump -- now resource-aware with location injection

## Open Questions

1. **How does `@resource()` mention detection work in `run_tool_calls()`?**
   - What we know: CONTEXT.md says `@resource()` mentions are navigable anywhere. The AI emits them in prose and tool results. They need to be detected and dispatched as navigation calls.
   - What's unclear: Does the AI emit them as `<run>source()</run>` blocks (which the existing eval loop handles), or as bare `@source()` text that needs a new regex? The former requires no new parsing; the latter requires adding `@resource()` to the tool tag system.
   - Recommendation: Start with `<run>source()</run>` -- the eval loop already handles this. `@resource()` in prose is a display convention (telling the AI what to call), not a dispatch mechanism. The AI reads `@source()` and responds with `<run>source()</run>`. If this creates too much friction, add bare `@resource()` dispatch as a follow-up.

2. **Where do ResourceHandle callables live in the namespace?**
   - What we know: They need to be in the REPL namespace alongside `ns`, `store`, `ai`, etc.
   - What's unclear: Are they top-level (`source`, `tasks`, `memory`) or nested under a container (`resources.source`, `resources.tasks`)?
   - Recommendation: Top-level, matching the `@source()` syntax from CONTEXT.md. `homespace()` is also top-level. `back()` is top-level. Seeded in `shell.py __init__` like `store` and `engine`. Add them to `_SKIP` in `_build_context()` so they don't clutter the namespace dump.

3. **How does the pruning algorithm count "tokens"?**
   - What we know: 500 token hard cap. ~4 chars/token heuristic.
   - What's unclear: Whether to use exact char count (2000 chars) or approximate token counting.
   - Recommendation: Use `len(text) // 4` as the token estimate. No tokenizer dependency. `CHAR_CAP = 2000` as the protocol constant, documented as "~500 tokens at 4 chars/token average." Adjust if empirical testing shows the heuristic is off by more than 20%.

## Integration Map

### Files to Create
| File | Purpose | Lines (est) |
|------|---------|-------------|
| `bae/repl/resource.py` | Resourcespace protocol, ResourceRegistry, NavigationState, ResourceError, ResourceHandle, entry/nav formatting, pruning algorithm | ~300 |
| `bae/repl/tools.py` | ToolRouter with homespace passthrough, `_exec_*` functions moved from ai.py | ~200 |

### Files to Modify
| File | Change | Risk |
|------|--------|------|
| `bae/repl/ai.py` | `run_tool_calls()` gains `router` param; `_build_context()` injects location; `_exec_*` functions move to tools.py (imports remain for backward compat) | MEDIUM -- core tool dispatch change |
| `bae/repl/shell.py` | Create ResourceRegistry, ToolRouter, ResourceHandles; seed namespace; add toolbar widget; pass router to AI | LOW -- additive init changes |
| `bae/repl/ai_prompt.md` | Append navigation section (~5-10 lines) | LOW -- text append |
| `bae/repl/toolbar.py` | Add `make_location_widget(shell)` function | LOW -- ~15 lines |
| `bae/repl/namespace.py` | Add resource handles to `_PRELOADED` or `_SKIP` | LOW -- ~3 lines |

### Existing Patterns Used
| Pattern | Source File | How Used |
|---------|------------|----------|
| Protocol + Registry | `channels.py` | Resourcespace + ResourceRegistry follows Channel + ChannelRouter |
| ContextVar state | `engine.py` | Navigation state ContextVar follows `_graph_ctx` |
| Callable namespace object | `namespace.py` NsInspector | ResourceHandle follows NsInspector's `__call__`/`__repr__` |
| Tool tag dispatch | `ai.py` run_tool_calls | ToolRouter wraps existing dispatch with resource scoping |
| Rich rendering pipeline | `views.py` `_rich_to_ansi` | Nav tree uses same Rich -> ANSI -> prompt_toolkit pipeline |
| Backward-compat param addition | `graph.py` arun(dep_cache=None) | `run_tool_calls(text, router=None)` follows same pattern |

## Sources

### Primary (HIGH confidence)
- `bae/repl/channels.py` -- Protocol+Registry pattern, ViewFormatter protocol, Channel/ChannelRouter
- `bae/repl/engine.py` -- ContextVar usage (_graph_ctx), GraphRegistry lifecycle
- `bae/repl/ai.py` -- Tool dispatch (run_tool_calls, _exec_*, _TOOL_EXEC), context building (_build_context), eval loop
- `bae/repl/namespace.py` -- NsInspector callable pattern, seed() namespace construction
- `bae/repl/shell.py` -- Integration points, namespace seeding, component wiring
- `bae/repl/views.py` -- Rich rendering pipeline (_rich_to_ansi), formatting patterns
- `bae/repl/store.py` -- SessionStore for externalized output storage
- `.planning/phases/31-resource-protocol-navigation/31-CONTEXT.md` -- Locked decisions on navigation feel, entry display, error messaging, pruning
- `.planning/REQUIREMENTS.md` -- RSP-01 through RSP-11 requirements
- `.planning/research/ARCHITECTURE.md` -- Component boundaries, data flow, integration points
- `.planning/research/PITFALLS.md` -- Critical pitfalls: desync, scoping leak, pruning destruction
- `.planning/research/FEATURES.md` -- Feature landscape, dependency graph, MVP recommendation
- `.planning/research/STACK.md` -- Zero new dependencies, stdlib-only approach

### Secondary (MEDIUM confidence)
- [Rich Tree documentation](https://rich.readthedocs.io/en/stable/tree.html) -- Tree rendering API for nav display
- [Python difflib](https://docs.python.org/3/library/difflib.html) -- get_close_matches for fuzzy name matching

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- zero new deps, all stdlib + existing, verified against pyproject.toml
- Architecture: HIGH -- all patterns directly from existing codebase (channels.py, engine.py, ai.py, namespace.py)
- Pitfalls: HIGH -- grounded in direct codebase analysis plus v7.0 research (PITFALLS.md, ARCHITECTURE.md)

**Research date:** 2026-02-16
**Valid until:** 2026-03-16 (stable -- no external dependencies to age)
