# Testing Patterns

**Analysis Date:** 2026-02-14

## Test Framework

**Runner:**
- pytest 8.0+
- Config: `pyproject.toml` `[tool.pytest.ini_options]`

**Assertion Library:**
- pytest built-in assertions
- No external assertion libraries

**Run Commands:**
```bash
pytest                     # Run all tests
pytest -k test_name        # Run specific test
pytest --run-e2e           # Run E2E tests (skipped by default)
pytest tests/repl/         # Run tests in directory
```

**Async Support:**
- pytest-asyncio 0.24+
- Config: `asyncio_mode = "auto"` (in `pyproject.toml`)
- Auto-detects async tests, no decorator needed

## Test File Organization

**Location:**
- Mirror source structure in `tests/` directory
- Co-located tests: Not used (all tests in `tests/`)

**Naming:**
- Pattern: `test_<module>.py`
- Examples: `test_graph.py`, `test_lm_protocol.py`, `test_fill_helpers.py`
- Integration tests: `test_<feature>_integration.py` (e.g., `test_ai_integration.py`)
- E2E tests: `test_<feature>_e2e.py` (e.g., `test_ootd_e2e.py`)

**Structure:**
```
tests/
├── __init__.py
├── conftest.py                    # Shared fixtures, markers, config
├── test_graph.py                  # Unit tests for bae/graph.py
├── test_lm_protocol.py            # Unit tests for bae/lm.py
├── test_fill_protocol.py          # Protocol tests
├── test_integration.py            # Integration tests
├── repl/
│   ├── __init__.py
│   ├── test_ai.py                 # Unit tests for bae/repl/ai.py
│   ├── test_ai_integration.py     # Integration tests
│   └── test_task_lifecycle.py     # Lifecycle tests
└── traces/
    └── json_structured_fill_reference.py  # Reference data
```

## Test Structure

**Suite Organization:**
```python
"""Tests for Graph class."""

from bae.graph import Graph
from bae.node import Node

# Test nodes (fixtures as module-level classes)
class Start(Node):
    query: str
    async def __call__(self, lm: LM) -> Process | Clarify:
        return await lm.decide(self)

class TestGraphDiscovery:
    """Tests for Graph topology discovery."""

    def test_discovers_all_nodes(self):
        graph = Graph(start=Start)
        assert graph.nodes == {Start, Clarify, Process, Review}

    def test_edges(self):
        graph = Graph(start=Start)
        edges = graph.edges
        assert edges[Start] == {Process, Clarify}

class TestGraphValidation:
    """Tests for Graph.validate()."""

    def test_valid_graph(self):
        graph = Graph(start=Start)
        issues = graph.validate()
        assert issues == []
```

**Patterns:**
- Group tests by class: `TestGraphDiscovery`, `TestGraphValidation`, `TestGraphRun`
- Class docstrings describe what's being tested
- Test method names: `test_<behavior>` (verb phrase describing behavior)
- Module-level test data/fixtures for reuse across test classes

## Fixtures

**conftest.py pattern:**
```python
"""Shared pytest configuration and markers."""

import pytest

def pytest_addoption(parser):
    parser.addoption("--run-e2e", action="store_true", default=False, help="run e2e tests")

def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: mark test as end-to-end (requires --run-e2e)")

def pytest_collection_modifyitems(config, items):
    if not config.getoption("--run-e2e"):
        skip_e2e = pytest.mark.skip(reason="need --run-e2e option to run")
        for item in items:
            if "e2e" in item.keywords:
                item.add_marker(skip_e2e)
```

**Test-level fixtures:**
```python
@pytest.fixture
def mock_lm():
    """Minimal LM stub."""
    return MagicMock()

@pytest.fixture
def mock_router():
    """Minimal ChannelRouter stub."""
    return MagicMock()

@pytest.fixture
def ai(mock_lm, mock_router):
    """AI instance with mocked dependencies."""
    return AI(lm=mock_lm, router=mock_router, namespace={})
```

**Fixture location:**
- Shared across module: in test file
- Shared across package: in `conftest.py`

## Mocking

**Framework:** `unittest.mock` (standard library)

**Patterns:**

**AsyncMock for async functions:**
```python
from unittest.mock import AsyncMock, patch

async def test_fill_returns_target_instance():
    backend = ClaudeCLIBackend()

    with patch.object(backend, "_run_cli_json", new_callable=AsyncMock) as mock_cli:
        mock_cli.return_value = {"name": "Alice", "greeting": "Hello Alice"}

        result = await backend.fill(Greet, {}, "Greet")

        assert isinstance(result, Greet)
        assert result.name == "Alice"
```

**MagicMock for sync dependencies:**
```python
from unittest.mock import MagicMock

def test_extract_executable():
    event = MagicMock()
    event.app.exit = MagicMock()
    event.app.invalidate = MagicMock()
```

**Capture arguments with side_effect:**
```python
captured_schema = {}

async def capture(prompt, schema):
    captured_schema.update(schema)
    return {"name": "Alice", "greeting": "Hi"}

with patch.object(backend, "_run_cli_json", side_effect=capture):
    await backend.fill(Greet, {}, "Greet")

assert "properties" in captured_schema
```

**What to Mock:**
- External APIs (LLM calls via `_run_cli_json`)
- I/O operations (subprocess, file access)
- Dependencies that slow down tests (database, network)

**What NOT to Mock:**
- Core domain logic (Graph execution, field resolution)
- Simple data transformations
- Type operations

## Test Data & Factories

**Pattern: Module-level test node classes:**
```python
# Test nodes for graph topology tests
class Start(Node):
    query: str
    async def __call__(self, lm: LM) -> Process | Clarify:
        return await lm.decide(self)

class Clarify(Node):
    question: str
    async def __call__(self, lm: LM) -> Start:
        return await lm.make(self, Start)
```

**Mock LM with sequence:**
```python
class MockLM:
    """Mock LM that returns nodes from a sequence."""

    def __init__(self, sequence: list[Node | None]):
        self.sequence = sequence
        self.index = 0

    async def make(self, node: Node, target: type) -> Node:
        result = self.sequence[self.index]
        self.index += 1
        return result

    async def decide(self, node: Node) -> Node | None:
        result = self.sequence[self.index]
        self.index += 1
        return result

# Usage:
lm = MockLM(sequence=[
    Process(task="do it"),
    Review(content="looks good"),
    None,
])
```

**Location:**
- Inline test data in test files (preferred)
- Reference traces in `tests/traces/` for complex data

## Coverage

**Requirements:** No enforced target

**View Coverage:**
```bash
pytest --cov=bae --cov-report=html
open htmlcov/index.html
```

**Gaps:**
- Not systematically tracked
- Focus on behavior coverage over line coverage

## Test Types

**Unit Tests:**
- Test single functions/classes in isolation
- Mock all external dependencies
- Fast (milliseconds per test)
- Examples: `test_graph.py::TestGraphDiscovery`, `test_lm_protocol.py::TestLMProtocol`

**Integration Tests:**
- Test multiple components together
- May use real dependencies (no external I/O)
- Examples: `test_ai_integration.py`, `test_namespace_integration.py`

**E2E Tests:**
- Full system tests with real LLM calls
- Marked with `@pytest.mark.e2e`
- Skipped by default, run with `pytest --run-e2e`
- Examples: `test_ootd_e2e.py`

## Common Patterns

**Async Testing:**
```python
class TestGraphRun:
    async def test_run_simple_path(self):
        graph = Graph(start=Start)
        lm = MockLM(sequence=[Process(task="do it"), None])

        result = await graph.arun(Start(query="hello"), lm=lm)

        assert isinstance(result, GraphResult)
        assert result.node is None
        assert len(result.trace) == 2
```

**Error Testing:**
```python
async def test_run_max_iters(self):
    graph = Graph(start=Infinite)
    lm = MockLM(sequence=[])

    with pytest.raises(BaeError, match="exceeded"):
        await graph.arun(Infinite(), lm=lm, max_iters=10)
```

**Testing Protocols:**
```python
class TestLMProtocol:
    """LM Protocol defines choose_type and fill."""

    def test_protocol_has_choose_type(self):
        """LM Protocol has a choose_type method."""
        assert hasattr(LM, "choose_type")

    def test_protocol_has_fill(self):
        """LM Protocol has a fill method."""
        assert hasattr(LM, "fill")
```

**Cleanup Testing (async resources):**
```python
@pytest.mark.asyncio
async def test_submit_creates_tracked_task(self, shell):
    """tm.submit() returns TrackedTask with RUNNING state."""
    async def noop():
        await asyncio.sleep(10)

    tt = shell.tm.submit(noop(), name="test:add", mode="nl")
    assert tt.state.value == "running"

    # Cleanup
    shell.tm.revoke(tt.task_id)
    try:
        await tt.task
    except asyncio.CancelledError:
        pass
```

**Mock event helpers:**
```python
def _mock_event(shell):
    """Build a mock prompt_toolkit event for key binding tests."""
    event = MagicMock()
    event.app.exit = MagicMock()
    event.app.invalidate = MagicMock()
    event.current_buffer.reset = MagicMock()

    _calls = []

    def _create_bg_task(coro):
        _calls.append(coro)
        coro.close()  # Prevent unawaited coroutine warning

    event.app.create_background_task = _create_bg_task
    event.app.create_background_task._calls = _calls
    return event
```

## Markers

**Custom markers (defined in `conftest.py`):**
```python
@pytest.mark.e2e
def test_full_graph_with_real_llm():
    """End-to-end test requiring real LLM."""
    # ...
```

**Usage:**
- `@pytest.mark.e2e`: End-to-end test (requires `--run-e2e`)
- `@pytest.mark.asyncio`: Auto-applied by pytest-asyncio

## Test Naming

**Function naming:**
- Pattern: `test_<what>_<condition>` or `test_<behavior>`
- Examples:
  - `test_discovers_all_nodes`
  - `test_single_type_returns_directly`
  - `test_fill_returns_target_instance`
  - `test_run_max_iters`

**Class naming:**
- Pattern: `Test<FeatureName>` or `Test<Class><Method>`
- Examples:
  - `TestGraphDiscovery`
  - `TestClaudeCLIBackendFill`
  - `TestExtractExecutable`

**Docstrings:**
Tests have descriptive docstrings:
```python
async def test_submit_creates_tracked_task(self, shell):
    """tm.submit() returns TrackedTask with RUNNING state."""
```

## Assertion Style

**Direct assertions:**
```python
assert result.node is None
assert len(result.trace) == 2
assert isinstance(result, GraphResult)
```

**Set comparison:**
```python
assert graph.nodes == {Start, Clarify, Process, Review}
assert edges[Start] == {Process, Clarify}
```

**Pattern matching:**
```python
with pytest.raises(BaeError, match="exceeded"):
    await graph.arun(Infinite(), lm=lm, max_iters=10)
```

**No assertion helpers:** No custom `assert_equal()` or similar. Use standard Python assertions.

---

*Testing analysis: 2026-02-14*
