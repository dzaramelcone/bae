# Testing Patterns

**Analysis Date:** 2026-02-04

## Test Framework

**Runner:**
- pytest 8.0+
- Config: `pyproject.toml` with `[tool.pytest.ini_options]`

**Assertion Library:**
- pytest's built-in `assert` statements

**Run Commands:**
```bash
pytest tests/                      # Run all tests
pytest tests/test_node.py          # Run specific test file
pytest tests/ -v                   # Verbose output
pytest tests/test_integration.py -s # Integration tests with output
```

**Async Testing:**
- pytest-asyncio 0.24+ configured with `asyncio_mode = "auto"` in `pyproject.toml`
- Allows `async def test_*()` functions automatically

## Test File Organization

**Location:**
- Separate test directory: `tests/` (not co-located with source)
- Path mapping: `bae/node.py` → `tests/test_node.py`, `bae/graph.py` → `tests/test_graph.py`

**Naming:**
- Test files: `test_*.py` prefix
- Test classes: `Test*` prefix (e.g., `TestNodeTopology`, `TestGraphDiscovery`)
- Test methods: `test_*` prefix (e.g., `test_successors_union`, `test_edges`)

**Structure:**
```
tests/
├── __init__.py           # Makes tests a package
├── test_node.py          # Node class tests
├── test_graph.py         # Graph class tests
└── test_integration.py   # Integration tests with real LM backends
```

## Test Structure

**Suite Organization:**
- Tests grouped into classes by functionality
- Example from `tests/test_node.py`:
  ```python
  class TestNodeTopology:
      def test_successors_union(self):
          """Start can go to Process or Clarify."""
          succs = Start.successors()
          assert succs == {Process, Clarify}

  class TestNodeCall:
      def test_call_with_lm_make(self):
          """Node can use lm.make to produce specific type."""
          expected = Process(task="do it")
          lm = MockLM(return_value=expected)
          # ...
  ```

**Patterns:**
- Setup: Create instances and mock LM objects directly in test methods
- Fixtures: pytest fixtures used in integration tests (see `tests/test_integration.py` lines 88-90)
- Teardown: Implicit (tests are isolated, no shared state)
- Assertions: Direct equality checks with meaningful error context

**Docstrings:**
- Every test has a docstring explaining what it tests
- Example: `"""Node can branch based on its own state."""`
- Docstring appears as test description in pytest output

## Mocking

**Framework:** Custom mock objects (no external mocking library)

**Patterns:**
- Define simple mock classes that implement the protocol interface
- Example from `tests/test_node.py`:
  ```python
  class MockLM:
      """Mock LM that returns predefined nodes."""

      def __init__(self, return_value: Node | None = None):
          self.return_value = return_value
          self.calls: list[Node] = []

      def make(self, node: Node, target: type) -> Node:
          self.calls.append(node)
          return self.return_value

      def decide(self, node: Node) -> Node | None:
          self.calls.append(node)
          return self.return_value
  ```

**Variations by test file:**
- `test_node.py`: MockLM stores return value, tracks calls
- `test_graph.py`: MockLM returns nodes from a sequence with index tracking
  ```python
  class MockLM:
      """Mock LM that returns nodes from a sequence."""

      def __init__(self, sequence: list[Node | None]):
          self.sequence = sequence
          self.index = 0

      def decide(self, node: Node) -> Node | None:
          result = self.sequence[self.index]
          self.index += 1
          return result
  ```

**What to Mock:**
- LM backends (PydanticAIBackend, ClaudeCLIBackend) - replace with MockLM for unit tests
- Don't mock Nodes themselves - test real Node subclasses
- Don't mock Graph internals - test Graph behavior directly

**What NOT to Mock:**
- Integration tests call real backends (PydanticAIBackend, ClaudeCLIBackend)
- Real Node instances passed to graph.run()
- Graph topology discovery uses real type hints

## Fixtures and Factories

**Test Data:**
- Node instances created inline in tests: `Start(query="test")`
- Test graph nodes defined in same file as tests (e.g., `Start`, `Process`, `Review` classes in `test_node.py`)
- Integration tests use realistic nodes: `Task(description="...")`, `Question(text="...")`

**Location:**
- Test nodes defined in test files themselves
- `tests/test_node.py` lines 24-52: `Start`, `Clarify`, `Process`, `Review` node classes
- `tests/test_graph.py` lines 29-77: Graph test node definitions
- `tests/test_integration.py` lines 18-74: Integration test node definitions

**Pytest Fixtures:**
- Located in integration tests for LM backends:
  ```python
  @pytest.fixture
  def lm(self):
      return PydanticAIBackend(model="anthropic:claude-sonnet-4-20250514")
  ```
- Fixtures create fresh LM instance per test method

## Coverage

**Requirements:** None enforced (not configured in `pyproject.toml`)

**View Coverage:** Not configured - would require `pytest-cov` plugin

## Test Types

**Unit Tests:**
- Scope: Individual classes and functions (Node topology, Graph structure)
- Approach: Use MockLM, test with predefined node sequences
- Location: `tests/test_node.py` (43 lines), `tests/test_graph.py` (160 lines)
- Example: Test that `successors()` correctly extracts types from return hints

**Integration Tests:**
- Scope: End-to-end graph execution with real LM backends
- Approach: Call actual pydantic-ai or Claude CLI APIs
- Location: `tests/test_integration.py` (190 lines)
- Requirements: ANTHROPIC_API_KEY for pydantic-ai tests, claude CLI installed for CLI tests
- Skipped if dependencies not available via `pytest.mark.skipif`

**E2E Tests:**
- Integrated into integration test file
- Calls `graph.run()` with real nodes and real LM backends
- Example `TestPydanticAIBackend.test_graph_run_task_decomposition` (lines 127-134)

## Common Patterns

**Async Testing:**
- Configured via pytest-asyncio with `asyncio_mode = "auto"`
- Tests can use `async def test_*()` automatically
- Not heavily used in current codebase (would be needed if backends used async)

**Error Testing:**
- Use pytest.raises() context manager
- Example from `tests/test_graph.py` lines 152-159:
  ```python
  def test_run_max_steps(self):
      """..."""
      graph = Graph(start=Infinite)
      lm = MockLM(sequence=[])

      with pytest.raises(RuntimeError, match="exceeded"):
          graph.run(Infinite(), lm=lm, max_steps=10)
  ```
- Tests the graph raises RuntimeError when max_steps exceeded

**Assertion Patterns:**
- Direct equality: `assert result == expected`
- Set membership: `assert succs == {Process, Clarify}`
- Type checks: `assert isinstance(result, Result)`
- Boolean checks: `assert Process.is_terminal() is True`
- None checks: `assert final is None`

**Test Organization by Layer:**

1. **Node Topology** (`TestNodeTopology` in test_node.py):
   - Tests type hint parsing: `successors()`, `is_terminal()`
   - Tests graph topology discovery

2. **Node Execution** (`TestNodeCall` in test_node.py):
   - Tests `__call__` method with injected LM
   - Tests routing logic based on node state

3. **Graph Discovery** (`TestGraphDiscovery` in test_graph.py):
   - Tests BFS traversal of graph from start node
   - Tests adjacency list construction

4. **Graph Validation** (`TestGraphValidation` in test_graph.py):
   - Tests detection of infinite loops (no terminal path)
   - Tests validation returns appropriate warnings

5. **Graph Execution** (`TestGraphRun` in test_graph.py):
   - Tests step-by-step execution with mocked LM
   - Tests max_steps enforcement
   - Tests terminal node detection

6. **Backend Integration** (`TestPydanticAIBackend`, `TestClaudeCLIBackend` in test_integration.py):
   - Tests `make()` produces correct typed output
   - Tests `decide()` picks from valid successors
   - Tests full graph execution with real LM

## Test Output

**Test pristine output:**
- No unexpected log messages or warnings
- Integration tests use `-s` flag to show stdout/stderr when needed
- Test comments explain setup and expectations

**Example test with clear documentation:**
```python
def test_run_multiple_steps(self):
    """Run a simple graph to completion."""
    graph = Graph(start=Start)

    # LM returns: Process -> Review -> None
    lm = MockLM(sequence=[
        Process(task="do it"),
        Review(content="looks good"),
        None,
    ])

    result = graph.run(Start(query="hello"), lm=lm)
    assert result is None
```

---

*Testing analysis: 2026-02-04*
