# Codebase Structure

**Analysis Date:** 2026-02-14

## Directory Layout

```
bae/
├── bae/                # Core package
│   ├── __init__.py     # Public API exports
│   ├── node.py         # Node base class
│   ├── graph.py        # Graph discovery and execution
│   ├── lm.py           # LM protocol and backends
│   ├── resolver.py     # Dependency injection
│   ├── markers.py      # Dep/Recall annotation markers
│   ├── exceptions.py   # Exception hierarchy
│   ├── result.py       # GraphResult dataclass
│   ├── cli.py          # CLI commands (graph show/export/run)
│   └── repl/           # Interactive REPL
│       ├── __init__.py
│       ├── shell.py    # CortexShell main loop
│       ├── ai.py       # AI assistant
│       ├── channels.py # Output routing
│       ├── namespace.py # Dynamic namespace
│       ├── store.py    # Session persistence
│       ├── tasks.py    # Background task management
│       ├── toolbar.py  # Status bar widgets
│       ├── complete.py # Tab completion
│       ├── exec.py     # Code execution
│       ├── bash.py     # Shell command dispatch
│       ├── modes.py    # Mode enum and cycle
│       └── ai_prompt.md # AI system prompt
├── tests/              # Test suite
│   ├── conftest.py
│   ├── test_*.py       # Unit/integration tests
│   ├── repl/           # REPL-specific tests
│   └── traces/         # Execution trace fixtures
├── examples/           # Example graphs
│   ├── ootd.py         # Weather outfit graph
│   ├── run_ootd_traced.py
│   └── fixtures/       # Example data
├── evals/              # LM convention evaluation
│   ├── prompts.py
│   ├── test_convention.py
│   └── results_*.txt
├── .planning/          # Planning docs (this file)
├── pyproject.toml      # Package metadata and deps
└── uv.lock             # Lockfile
```

## Directory Purposes

**bae/**
- Purpose: Core package implementation
- Contains: Node, Graph, LM, resolver, CLI
- Key files: `node.py` (base class), `graph.py` (execution), `lm.py` (LM backends)

**bae/repl/**
- Purpose: Interactive REPL environment
- Contains: CortexShell (prompt_toolkit), AI assistant, mode switching
- Key files: `shell.py` (main loop), `ai.py` (AI integration), `namespace.py` (eval context)

**tests/**
- Purpose: Test suite (pytest)
- Contains: Unit tests, integration tests, fixtures
- Key files: `test_graph.py`, `test_resolver.py`, `test_fill_protocol.py`

**tests/repl/**
- Purpose: REPL-specific tests
- Contains: Tests for AI, toolbar, namespace, shell
- Key files: `test_ai.py`, `test_toolbar.py`

**examples/**
- Purpose: Example graph implementations
- Contains: Weather outfit recommendation graph, fixtures
- Key files: `ootd.py` (weather outfit graph)

**evals/**
- Purpose: LM output convention evaluation
- Contains: Prompts for testing LM parsing conventions, result dumps
- Key files: `test_convention.py`, `prompts.py`

**tests/traces/**
- Purpose: Saved execution traces for debugging
- Contains: JSON/text dumps of graph execution
- Generated: Yes
- Committed: No (gitignored)

## Key File Locations

**Entry Points:**
- `bae/cli.py`: CLI entrypoint (`main()`)
- `bae/repl/__init__.py`: REPL entrypoint (`launch()`)
- `bae/__init__.py`: Module import entrypoint

**Configuration:**
- `pyproject.toml`: Package metadata, dependencies, tool config
- `.planning/config.json`: GSD planning config

**Core Logic:**
- `bae/node.py`: Node base class
- `bae/graph.py`: Graph execution engine
- `bae/resolver.py`: Dependency injection
- `bae/lm.py`: LM backends

**Testing:**
- `tests/conftest.py`: Pytest fixtures
- `tests/test_*.py`: Test modules

## Naming Conventions

**Files:**
- Lowercase with underscores: `test_fill_protocol.py`
- Module names match primary class: `node.py` (Node), `graph.py` (Graph)

**Directories:**
- Lowercase: `bae/`, `tests/`, `examples/`
- Subpackages: `bae/repl/`

**Classes:**
- PascalCase: `Node`, `Graph`, `ClaudeCLIBackend`
- Protocols: `LM` (all caps for brevity)

**Functions:**
- snake_case: `resolve_fields()`, `classify_fields()`
- Private/internal: Leading underscore `_has_ellipsis_body()`

**Constants:**
- UPPER_SNAKE_CASE: `LM_KEY`, `MODE_COLORS`, `TASKS_PER_PAGE`

## Where to Add New Code

**New Node Type:**
- Primary code: User code (outside bae package) or `examples/*.py`
- Tests: `tests/test_integration.py` or new `tests/test_myfeature.py`

**New LM Backend:**
- Implementation: `bae/lm.py` (new class implementing LM protocol)
- Tests: `tests/test_lm_protocol.py`

**New Graph Feature:**
- Implementation: `bae/graph.py` (modify Graph class)
- Tests: `tests/test_graph.py`

**New Resolver Feature:**
- Implementation: `bae/resolver.py`
- Tests: `tests/test_resolver.py`, `tests/test_dep_injection.py`

**New CLI Command:**
- Implementation: `bae/cli.py` (new Typer command)
- Tests: Not currently tested (CLI uses subprocess, would need integration test)

**New REPL Feature:**
- Implementation: `bae/repl/shell.py` or new module in `bae/repl/`
- Tests: `tests/repl/test_*.py`

**Utilities:**
- Shared helpers: Add to relevant module (`bae/graph.py` for graph utils, `bae/lm.py` for schema utils)

## Special Directories

**.planning/**
- Purpose: GSD planning documents and metadata
- Generated: Partially (by GSD commands)
- Committed: Yes

**.venv/**
- Purpose: Virtual environment
- Generated: Yes (by uv/pip)
- Committed: No

**__pycache__/**
- Purpose: Python bytecode cache
- Generated: Yes (by Python)
- Committed: No

**tests/traces/**
- Purpose: Execution trace dumps for debugging
- Generated: Yes (by tests with SAVE_TRACE=1)
- Committed: No

**.bae/**
- Purpose: REPL session storage
- Generated: Yes (by bae REPL)
- Committed: No

---

*Structure analysis: 2026-02-14*
