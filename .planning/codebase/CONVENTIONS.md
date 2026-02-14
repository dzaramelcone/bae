# Coding Conventions

**Analysis Date:** 2026-02-14

## Naming Patterns

**Files:**
- Snake case: `test_graph.py`, `ai_prompt.md`, `task_lifecycle.py`
- Descriptive, domain-focused: `resolver.py`, `exceptions.py`, `markers.py`
- Test files: `test_<module>.py` pattern (e.g., `test_lm_protocol.py`)

**Functions:**
- Snake case for functions/methods: `resolve_fields()`, `build_context()`, `extract_executable()`
- Private/internal functions prefixed with `_`: `_get_base_type()`, `_build_plain_model()`, `_has_ellipsis_body()`
- Async functions: `async def arun()`, `async def async_exec()`
- Naming by domain purpose, not implementation: `fill()` not `llm_populate()`, `resolve_fields()` not `inject_deps()`

**Variables:**
- Snake case: `start_node`, `dep_cache`, `target_type`, `plain_fields`
- Single letter allowed in comprehensions and short scopes: `t`, `k`, `v`
- Descriptive over abbreviated: `resolved` not `res`, `captured_schema` not `cap_sch`

**Types:**
- PascalCase for classes: `Node`, `Graph`, `ClaudeCLIBackend`, `TaskManager`
- PascalCase for Pydantic models: `Weather`, `GraphResult`, `TrackedTask`
- PascalCase for exceptions: `BaeError`, `DepError`, `RecallError`, `FillError`
- PascalCase for Nodes (graph node types): `Start`, `Process`, `Review`, `AlphaNode`, `BetaNode`

## Code Style

**Formatting:**
- Tool: Ruff (configured in `pyproject.toml`)
- Line length: 100 characters
- Target version: Python 3.12+ (requires 3.14 for PEP 649)

**Linting:**
- Tool: Ruff
- Rules enabled: `["E", "F", "I", "UP"]`
  - E: pycodestyle errors
  - F: Pyflakes (unused imports, undefined names)
  - I: isort (import ordering)
  - UP: pyupgrade (modern Python syntax)

**Docstrings:**
- Multi-line docstrings for modules, classes, public functions
- Format: Standard triple-quoted strings with description first
- Include Args/Returns/Raises sections for complex functions:
  ```python
  def resolve_fields(node_cls: type) -> dict[str, str]:
      """Classify each field of a Node subclass by its annotation marker.

      Args:
          node_cls: A Node subclass whose fields to classify.

      Returns:
          Dict mapping field name to "dep", "recall", or "plain".
      """
  ```
- Short functions may omit docstrings if intent is clear from name

## Import Organization

**Order:**
1. Future imports: `from __future__ import annotations`
2. Standard library imports (sorted)
3. Third-party imports (sorted)
4. Local imports (sorted)

**Example from `bae/graph.py`:**
```python
import asyncio
import logging
import types
from collections import deque
from typing import Annotated, Any, get_args, get_origin, get_type_hints

from bae.exceptions import BaeError, DepError, RecallError
from bae.lm import LM
from bae.node import Node, _has_ellipsis_body, _wants_lm
from bae.resolver import LM_KEY, resolve_fields
from bae.result import GraphResult
```

**Path Aliases:**
- None used (no `@` or `~` aliases)
- Absolute imports preferred: `from bae.node import Node`
- Relative imports avoided

**TYPE_CHECKING pattern:**
Used to avoid circular imports:
```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bae.node import Node
    from bae.lm import LM
```

## Error Handling

**Patterns:**
- Custom exception hierarchy rooted at `BaeError` (in `bae/exceptions.py`)
- Always chain exceptions with `raise ... from e` or set `__cause__`
- Specialized exceptions for different failure modes:
  - `RecallError`: Missing field in trace
  - `DepError`: Dependency function failed
  - `FillError`: LLM validation failed
  - `BaeLMError`: LLM API failure
  - `BaeParseError`: Validation/parsing failure

**Re-raising:**
```python
except RecallError:
    raise  # Already correct type
except Exception as e:
    err = DepError(
        f"{e} failed on {current.__class__.__name__}",
        node_type=current.__class__,
        cause=e,
    )
    err.trace = trace
    raise err from e
```

**Cleanup protection:**
Always catch and re-raise `CancelledError`, `KeyboardInterrupt`, `SystemExit`:
```python
except (asyncio.CancelledError, KeyboardInterrupt, SystemExit):
    raise
except BaseException:
    # handle error
```

**Silent failures:**
Used sparingly, only for expected OS errors:
```python
except (ProcessLookupError, OSError):
    pass  # Process already dead
```

## Logging

**Framework:** Standard library `logging`

**Pattern:**
```python
import logging

logger = logging.getLogger(__name__)

logger.debug("Resolved %d fields on %s", len(resolved), current.__class__.__name__)
```

**Usage:**
- `logger.debug()` for execution flow tracing (used in `bae/graph.py`)
- Module-level logger: `logger = logging.getLogger(__name__)`
- Never `print()` in library code (only in CLI/REPL user output)
- In REPL shell, capture logging to channel router:
  ```python
  graph_logger = logging.getLogger("bae.graph")
  handler = logging.StreamHandler(buf)
  graph_logger.addHandler(handler)
  ```

## Comments

**When to Comment:**
- Complex type manipulation: `# Handle union types (X | None)`
- Non-obvious algorithms: `# Propagate backwards: if a node can reach a terminal...`
- Why not what: `# Skip loading project/user settings` not `# Set --setting-sources to empty`
- Edge cases: `# Multiple non-None types - return first one (edge case)`

**Avoid:**
- Temporal context ("changed from X", "was Y before")
- Implementation history
- Redundant explanations of obvious code

**Section markers:**
```python
# ── Fill helpers ─────────────────────────────────────────────────────────
```
Used in longer files like `bae/lm.py` to separate concerns.

## Function Design

**Size:**
- No hard limit, but functions over 50 lines should have clear sections
- Extract helpers when logic can be named: `_build_context()`, `_get_routing_strategy()`
- Private helpers prefixed with `_`

**Parameters:**
- Keyword-only for complex functions: `def __init__(self, *, lm: LM, router: ChannelRouter, ...)`
- Type hints always present
- Use `|` syntax for unions: `Node | None` not `Optional[Node]`
- Use defaults for optional params: `max_iters: int = 10`

**Return Values:**
- Explicit return type hints
- Return None explicitly when appropriate
- Use tuples for multiple values: `def extract_executable(text: str) -> tuple[str | None, int]`

## Module Design

**Exports:**
- No explicit `__all__` in most modules
- Classes/functions intended as public API are imported at package level (`bae/__init__.py`)
- Private modules/functions marked with `_` prefix

**Module docstrings:**
All modules start with a module-level docstring:
```python
"""Graph discovery and execution.

The Graph class discovers topology from Node type hints and handles execution.
"""
```

**Barrel Files:**
Not used. Imports are direct: `from bae.graph import Graph` not `from bae import Graph` (unless exported in `__init__.py`)

## Type Annotations

**Coverage:**
- All public functions have type hints
- Private functions (`_`) have type hints
- Use `typing.Annotated` for metadata: `Annotated[str, Dep(fetch_data)]`
- Use `get_type_hints(include_extras=True)` to preserve `Annotated` metadata

**Modern syntax:**
- Union with `|`: `str | None`
- Generic with `[]`: `list[str]`, `dict[str, int]`
- Requires Python 3.10+

**Protocol pattern:**
```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class LM(Protocol):
    async def fill(self, target: type[T], ...) -> T:
        ...
```

## Async Conventions

**Naming:**
- Sync wrapper: `def run()`
- Async implementation: `async def arun()`

**Pattern:**
```python
def run(self, start_node: Node, lm: LM | None = None, max_iters: int = 10) -> GraphResult:
    """Execute the graph synchronously. Cannot be called from within a running event loop."""
    return asyncio.run(self.arun(start_node, lm=lm, max_iters=max_iters))

async def arun(self, start_node: Node, lm: LM | None = None, max_iters: int = 10) -> GraphResult:
    """Execute the graph asynchronously. Use when already in an event loop."""
    # implementation
```

**Execution:**
- Use `await` for async calls
- Use `asyncio.create_subprocess_exec()` for external processes
- Handle `asyncio.TimeoutError` explicitly
- Always cancel tasks on cleanup

---

*Convention analysis: 2026-02-14*
