# Coding Conventions

**Analysis Date:** 2026-02-04

## Naming Patterns

**Files:**
- Lowercase with underscores: `node.py`, `graph.py`, `lm.py`, `compiler.py`
- Test files use `test_` prefix: `test_node.py`, `test_graph.py`, `test_integration.py`

**Classes:**
- PascalCase: `Node`, `Graph`, `NodeConfig`, `LM`, `PydanticAIBackend`, `ClaudeCLIBackend`, `CompiledGraph`
- Protocol classes use plain names: `LM` (Protocol)
- Domain-based naming (what they represent, not implementation): `Start`, `Process`, `Review`, `Clarify`, `Question`, `Answer` instead of "Node1", "Step2", etc.

**Functions:**
- snake_case: `successors()`, `is_terminal()`, `_discover()`, `to_mermaid()`, `node_to_signature()`, `compile_graph()`
- Private/internal functions use leading underscore: `_extract_types_from_hint()`, `_hint_includes_none()`, `_get_agent()`, `_node_to_prompt()`, `_build_schema()`, `_run_cli()`

**Variables:**
- snake_case: `start_node`, `node_cls`, `cache_key`, `type_list`, `successor`, `max_steps`
- Abbreviations preserved: `lm` (language model), `doc`, `succ` (successor)

**Type Variables:**
- Single uppercase letter: `T = TypeVar("T", bound="Node")`

## Code Style

**Formatting:**
- 100 character line length (from `pyproject.toml`)
- PEP 8 style with some modern Python features
- Target Python 3.12 (from `pyproject.toml`)

**Linting:**
- Ruff configured with rules: E (errors), F (Pyflakes), I (import sorting), UP (modernize)
- Enforced via `[tool.ruff.lint]` in `pyproject.toml`

**Future annotations:**
- Use `from __future__ import annotations` at top of files for forward references
- Example: `bae/node.py`, `bae/lm.py`

## Import Organization

**Order:**
1. `from __future__ import annotations` (deferred evaluation)
2. Standard library imports (`import types`, `from typing import ...`, `from collections import deque`)
3. Third-party imports (`from pydantic import ...`, `from pydantic_ai import Agent`)
4. Local imports (`from bae.node import Node`, `from bae.graph import Graph`)

**TYPE_CHECKING guard:**
- Use `if TYPE_CHECKING:` for imports only needed for type hints
- Example in `bae/node.py`:
  ```python
  if TYPE_CHECKING:
      from bae.lm import LM
  ```
- Prevents circular imports while maintaining type information

**Path Aliases:**
- Use absolute imports with full package path: `from bae.node import Node`
- No relative imports (e.g., no `from .node import Node`)

## Error Handling

**Patterns:**
- Raise specific exception types with descriptive messages:
  - `ValueError`: Invalid argument or state (e.g., node with no successors and not terminal)
  - `RuntimeError`: Runtime error (e.g., graph execution timeout, CLI subprocess failure)
  - `NotImplementedError`: Unfinished features (DSPy compilation phase)

**String formatting:**
- Use f-strings with {class_name} patterns: `f"{node.__class__.__name__} has no successors"`
- Include context in error messages for debugging

**Try-except blocks:**
- Located in `bae/lm.py` ClaudeCLIBackend._run_cli():
  ```python
  try:
      result = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout)
  except subprocess.TimeoutExpired:
      raise RuntimeError(f"Claude CLI timed out after {self.timeout}s")
  ```
- Re-raise with more context where applicable

## Logging

**Framework:** None - uses direct output through exception messages and docstrings

**Patterns:**
- Use docstrings for documentation and context
- Prompt construction includes current state and context (see `_node_to_prompt()` in `bae/lm.py`)
- Debug output through print would go in test output (not observed in core code)

## Comments

**When to Comment:**
- Docstrings on all public functions and classes
- Inline comments only for non-obvious logic or workarounds

**Docstring Style:**
- Module-level docstring at top of each file
- Google-style docstrings with Args/Returns/Raises sections
- Example from `bae/graph.py`:
  ```python
  def run(
      self,
      start_node: Node,
      lm: LM,
      max_steps: int = 100,
  ) -> Node | None:
      """Execute the graph starting from the given node.

      Args:
          start_node: Initial node instance with fields populated.
          lm: Language model backend for producing nodes.
          max_steps: Maximum execution steps (prevents infinite loops).

      Returns:
          None if terminated normally, or raises if max_steps exceeded.
      """
  ```

**JSDoc/TSDoc:** Not applicable - Python project

## Function Design

**Size:** Functions are compact and focused
- `_extract_types_from_hint()`: 8 lines
- `_hint_includes_none()`: 8 lines
- `successors()`: 2 lines (with docstring)
- `is_terminal()`: 2 lines (with docstring)

**Parameters:**
- Use type hints throughout
- Optional parameters have defaults
- LM is typically injected as parameter

**Return Values:**
- Explicit return type hints: `-> Node | None`, `-> set[type]`, `-> dict[type[Node], set[type[Node]]]`
- Modern union syntax: `X | Y` instead of `Union[X, Y]`
- Functions return explicit values or None

## Module Design

**Exports:**
- Public API defined in `bae/__init__.py`:
  ```python
  __all__ = ["Node", "NodeConfig", "Graph", "LM", "PydanticAIBackend", "ClaudeCLIBackend"]
  ```
- Each module has clear public interface

**Barrel Files:**
- Single barrel at package root (`bae/__init__.py`)
- Re-exports core classes for convenient import: `from bae import Node, Graph`

**Module cohesion:**
- `bae/node.py`: Node base class and topology extraction helpers
- `bae/graph.py`: Graph discovery and execution
- `bae/lm.py`: LM protocol and implementations
- `bae/compiler.py`: DSPy compilation support (stub)

## Type Hints

**Modern Python:**
- Use `X | Y` union syntax (requires Python 3.10+, enforced via `from __future__ import annotations`)
- Use `type[Node]` instead of `Type[Node]`
- Use `ClassVar` for class variables
- `get_type_hints()` and `get_args()` for runtime type introspection

**Examples:**
```python
@classmethod
def successors(cls) -> set[type[Node]]:
    """Get node types that can follow this node."""
    ...

def run(
    self,
    start_node: Node,
    lm: LM,
    max_steps: int = 100,
) -> Node | None:
    ...
```

---

*Convention analysis: 2026-02-04*
