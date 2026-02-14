# Technology Stack

**Analysis Date:** 2026-02-14

## Languages

**Primary:**
- Python 3.14.3 - All application code

**Secondary:**
- None

## Runtime

**Environment:**
- Python 3.14+

**Package Manager:**
- uv - Modern Python package manager
- Lockfile: `uv.lock` present

## Frameworks

**Core:**
- Pydantic >=2.0 - Runtime type validation and schema generation for nodes
- Typer >=0.12 - CLI framework for main command interface

**Testing:**
- pytest >=8.0 - Test runner
- pytest-asyncio >=0.24 - Async test support

**Build/Dev:**
- Hatchling - Build backend (defined in pyproject.toml)
- Ruff >=0.8 - Linter and formatter

**REPL/Interactive:**
- prompt-toolkit >=3.0.50 - Rich interactive shell with completion, history
- Pygments >=2.19 - Syntax highlighting
- Rich >=14.3 - Terminal formatting and rendering

## Key Dependencies

**Critical:**
- Pydantic >=2.0 - Core type system for Node definitions, schema generation, and LM protocol
- Claude CLI (external) - LLM backend for node population and type selection

**Infrastructure:**
- prompt-toolkit >=3.0.50 - Powers the cortex REPL (bae/repl/)
- Typer >=0.12 - Main CLI entry point (`bae` command)

## Configuration

**Environment:**
- No .env files detected
- Configuration passed via CLI flags or through shell environment
- ANTHROPIC_API_KEY required for Claude CLI integration (external dependency)
- CLAUDECODE environment variable explicitly filtered in AI subprocess calls (`bae/repl/ai.py:214`)

**Build:**
- `pyproject.toml` - Project metadata, dependencies, tool config
- `[tool.ruff]` - Linter config (line-length: 100, target: py312)
- `[tool.pytest.ini_options]` - Test config (asyncio_mode: auto, testpaths: tests)

## Platform Requirements

**Development:**
- Python >=3.14
- uv package manager
- Claude CLI (external binary) for LLM integration

**Production:**
- Not applicable - library/REPL tool, not a deployed service
- CLI entry point: `bae = "bae.cli:main"` installed via pip/uv

---

*Stack analysis: 2026-02-14*
