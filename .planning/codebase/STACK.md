# Technology Stack

**Analysis Date:** 2026-02-04

## Languages

**Primary:**
- Python 3.14+ - All source code and tooling. Requires Python 3.14 for PEP 649 (deferred annotation evaluation) support for forward references in type hints.

## Runtime

**Environment:**
- CPython 3.14.2

**Package Manager:**
- `uv` - Fast Python package manager with lockfile support
- Lockfile: `uv.lock` (present)

## Frameworks

**Core:**
- Pydantic 2.12.5 - Type validation and serialization for Node classes (BaseModel inheritance)
- pydantic-ai 1.53.0 - LLM abstraction layer providing structured output from language models

**ML/Optimization:**
- DSPy 3.1.2 - Prompt optimization and program synthesis framework (partially integrated in `bae/compiler.py`, not yet fully wired)

**Utilities:**
- incant 25.1.0 - Dependency injection framework (listed in dependencies but not currently used in codebase)

**Testing:**
- pytest 8.0+ - Test framework
- pytest-asyncio 0.24+ - Async test support

**Build/Dev:**
- ruff 0.8+ - Linting and code formatting
- hatchling - Build backend for packaging

## Key Dependencies

**Critical:**
- Pydantic (2.12.5) - Type validation. All Node classes inherit from `BaseModel`. Core to type safety of agent graphs.
- pydantic-ai (1.53.0) - LLM integration. Provides `Agent` class for structured LLM output. Used by `PydanticAIBackend` in `bae/lm.py`.

**Infrastructure:**
- Anthropic SDK (0.77.1) - Claude API access (transitively required by pydantic-ai when using Anthropic models)

**Supporting:**
- dspy (3.1.2) - For future optimization features
- incant (25.1.0) - Included but unused; available for dependency injection if needed

## Configuration

**Environment:**
- Python version requirement enforced in `pyproject.toml` (requires-python = ">=3.14")
- Ruff configured for 100-character line length and specific lint rules (E, F, I, UP)
- pytest configured with asyncio_mode = "auto" and testpaths pointing to `tests/`

**Build:**
- `pyproject.toml` - Single source of truth for project metadata, dependencies, and tool config
- No additional build configuration files

## Platform Requirements

**Development:**
- Python 3.14+ (must have PEP 649 support)
- `uv` package manager installed
- Claude CLI tool available (for `ClaudeCLIBackend` tests in `tests/test_integration.py`)
- `ANTHROPIC_API_KEY` environment variable (for PydanticAIBackend tests)

**Production:**
- Python 3.14+ runtime
- Network access to LLM provider (Anthropic API for pydantic-ai backend, or local Claude CLI)

## Optional Dependencies

**Development group** (installed via `uv pip install -e ".[dev]"`):
- pytest>=8.0
- pytest-asyncio>=0.24
- ruff>=0.8

---

*Stack analysis: 2026-02-04*
