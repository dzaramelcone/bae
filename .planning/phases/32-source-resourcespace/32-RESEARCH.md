# Phase 32: Source Resourcespace - Research

**Researched:** 2026-02-16
**Domain:** Python project introspection, AST-based source manipulation, module navigation
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Module-based addressing
- All paths use Python module notation: `read('bae.ai')`, `glob('bae.cortex.*')`
- No raw file paths — source is a semantic interface over the Python project
- Non-Python package data (templates, data files) also accessible within the module tree
- Dotted paths drill into symbols: `read('bae.ai.Agent')` shows the Agent class source
- Navigation also works: `source.bae.ai()` enters the module, then `read('Agent')` for details
- Both approaches work — dotted reads for quick lookups, navigation for exploration

#### Module display
- `read()` on a module from root level shows: high-level interface summary — major methods/functions/types, docstrings truncated to 1 line
- `read()` when navigated inside a module shows full source
- Module summaries include docstring (1 line) + class/function counts: `bae.ai — AI agent core (3 classes, 12 functions)`
- Glob/grep results use module paths: `bae.ai:42: def send()`
- Package hierarchy uses standard tree navigation — see current level, navigate deeper

#### Path safety
- Traversal escapes (`../`) and out-of-scope paths rejected with clear ResourceError
- No filesystem paths exposed — the module-based interface is the only addressing scheme

#### Entry experience
- `source()` entry shows: subresources (deps, config, tests) + brief descriptions
- Packages discoverable via `read()` which shows top-level packages with docstring + counts
- When output exceeds token budget, tell agent to narrow the search rather than silently pruning

#### Subresources
- `source.deps()` — list/add/remove dependencies. Modifies pyproject.toml, hotswaps module at runtime, uses svcs for resolution under the hood
- `source.config()` — structured access to pyproject.toml sections only
- `source.tests()` — browse test modules + run tests. Test results are a navigable subresource
- `source.meta()` — read/edit the SourceResourcespace implementation itself (MVP scope)

#### Edit operations
- Write/edit work from any navigation level (no navigate-first requirement)
- Semantic edits: `edit('bae.ai.Agent.send', new_source=...)` — symbol-level, not string replacement
- `write()` for new modules accepts raw Python source; auto-updates `__init__.py` to expose new module
- Syntax validation via `ast.parse` before writing — reject invalid Python
- Auto hot-reload after edit via `importlib.reload()`
- If reload fails (import error, circular deps): auto rollback to last-good state, report helpful error describing what went wrong

#### Undo + history
- Source provides an undo affordance — implementation details (git, rope, etc.) abstracted behind the interface
- Git only for persistent history is fine; undo is an operational convenience

### Claude's Discretion
- Navigation chrome (breadcrumbs, sibling display when inside a package)
- Exact pruning strategy for narrowing guidance
- Internal tool translation (module patterns to file operations under the hood)
- Rope vs AST vs other libraries for semantic editing internals

### Deferred Ideas (OUT OF SCOPE)
- meta() as a full representation-tuning interface (configurable display, affordance control) — pattern established here, fleshed out across all resourcespaces later
- Non-Python config files (.env, etc.) — pyproject.toml only for now
</user_constraints>

## Summary

This phase builds the first concrete resourcespace on top of the Phase 31 protocol foundation. The source resourcespace provides a semantic Python project interface where the agent navigates modules, packages, and symbols using dotted Python notation instead of raw file paths. It implements the full Resourcespace protocol (enter/nav/read + write/edit/glob/grep) and includes four subresourcespaces: deps, config, tests, and meta.

The standard library provides everything needed for the core implementation. `ast` handles source parsing, symbol extraction, and syntax validation. `inspect.getsource()` retrieves symbol-level source. `importlib` + `pkgutil` provide module discovery and hot-reload. `tomllib` (stdlib) reads pyproject.toml; `tomlkit` (new dependency) is needed for style-preserving writes. Git provides undo via subprocess calls. No rope or other heavyweight libraries are needed -- AST line numbers give us precise symbol boundaries for editing.

**Primary recommendation:** Build the SourceResourcespace as a single module (`bae/repl/source.py`) implementing the Resourcespace protocol, with subresourcespaces as inner classes or companion classes in the same file. Use `ast` for all source introspection and symbol-level editing. Use git for undo history. Defer svcs integration for deps until svcs is actually a dependency (use direct subprocess `uv` calls instead).

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `ast` | stdlib | Parse Python source, extract symbols, validate syntax, locate symbol line ranges | Built-in, zero deps, handles all AST operations needed |
| `inspect` | stdlib | Get source code of live objects via `getsource()` | Built-in, reliable for installed/importable modules |
| `importlib` | stdlib | Module import, `reload()` for hot-reload after edits | Built-in, the standard mechanism for runtime module management |
| `pkgutil` | stdlib | `walk_packages()` for package/module discovery | Built-in, canonical way to enumerate installed packages |
| `tomllib` | stdlib (3.11+) | Read pyproject.toml for config/deps subresources | Built-in since Python 3.11, read-only TOML parser |
| `tomlkit` | 0.13+ | Write pyproject.toml preserving comments/formatting | Style-preserving TOML r/w, used by Poetry; needed for deps.add/remove |
| `pathlib` | stdlib | File path manipulation under the hood | Built-in |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `subprocess` | stdlib | Git operations (commit, diff, checkout) for undo | When undo() is called to revert last edit |
| `subprocess` | stdlib | `uv add`/`uv remove` for dependency management | When deps.add()/deps.remove() are called |
| `difflib` | stdlib | Generate diffs for edit previews | When showing what changed after an edit |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `ast` line-range editing | `rope` (python-rope) | Rope provides rename/refactor but is heavyweight (500KB+), slow startup, and overkill for symbol-level source replacement. AST end_lineno (Python 3.8+) gives precise symbol boundaries. |
| `tomlkit` | Manual string manipulation | tomlkit preserves comments and formatting on round-trip; manual manipulation would lose them or be fragile |
| `git` for undo | In-memory history stack | Git provides persistent cross-session history; in-memory stack is simpler but lost on restart. Git is already available. |

**Installation:**
```bash
uv add tomlkit
```

## Architecture Patterns

### Recommended Module Structure
```
bae/repl/source.py          # SourceResourcespace + subresource classes
tests/test_source.py         # Tests for source resourcespace
```

### Pattern 1: Module Path Resolution
**What:** Translate dotted Python module paths to filesystem paths and back.
**When to use:** Every tool call -- this is the core translation layer.
**Example:**
```python
# Verified via testing in this research session
def _module_to_path(project_root: Path, dotted: str) -> Path:
    """Translate 'bae.repl.ai' to /project/bae/repl/ai.py (or __init__.py for packages)."""
    parts = dotted.split(".")
    candidate = project_root / Path(*parts)
    if candidate.is_dir() and (candidate / "__init__.py").exists():
        return candidate / "__init__.py"
    py = candidate.with_suffix(".py")
    if py.exists():
        return py
    raise ResourceError(f"Module '{dotted}' not found")

def _path_to_module(project_root: Path, filepath: Path) -> str:
    """Translate /project/bae/repl/ai.py to 'bae.repl.ai'."""
    rel = filepath.relative_to(project_root)
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    elif parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    return ".".join(parts)
```

### Pattern 2: AST-Based Symbol Extraction
**What:** Use `ast.parse()` + `ast.get_docstring()` to build module summaries without importing.
**When to use:** `read()` at summary level (from root, not navigated in).
**Example:**
```python
# Verified: ast provides lineno, end_lineno, docstrings for all nodes
def _module_summary(source: str, module_path: str) -> str:
    tree = ast.parse(source)
    docstring = ast.get_docstring(tree) or ""
    first_line = docstring.splitlines()[0] if docstring else "(no docstring)"

    classes = [n for n in ast.iter_child_nodes(tree) if isinstance(n, ast.ClassDef)]
    functions = [n for n in ast.iter_child_nodes(tree)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and not n.name.startswith("_")]

    return f"{module_path} -- {first_line} ({len(classes)} classes, {len(functions)} functions)"
```

### Pattern 3: Symbol-Level Source Editing
**What:** Replace a specific symbol (class, function) in source using AST line numbers.
**When to use:** `edit('bae.ai.Agent.send', new_source=...)`.
**Example:**
```python
# Verified: ast nodes have .lineno and .end_lineno on Python 3.8+
def _replace_symbol(source: str, symbol_name: str, new_source: str) -> str:
    """Replace a top-level or nested symbol's source lines."""
    tree = ast.parse(source)
    lines = source.splitlines(True)

    target = _find_symbol(tree, symbol_name)  # walks AST, returns node
    if target is None:
        raise ResourceError(f"Symbol '{symbol_name}' not found")

    # Validate new source parses cleanly
    ast.parse(new_source)

    # Replace lines (1-indexed lineno to 0-indexed list)
    new_lines = lines[:target.lineno - 1] + [new_source + "\n"] + lines[target.end_lineno:]
    result = "".join(new_lines)

    # Validate the whole module still parses
    ast.parse(result)
    return result
```

### Pattern 4: Hot-Reload with Rollback
**What:** After writing edited source, reload the module; rollback on failure.
**When to use:** Every write/edit operation.
**Example:**
```python
# Verified: importlib.reload raises on broken imports but module object survives
def _hot_reload(module_path: str, filepath: Path, old_source: str):
    """Reload module after edit; rollback to old_source on failure."""
    try:
        mod = importlib.import_module(module_path)
        importlib.reload(mod)
    except Exception as e:
        # Rollback: restore old source
        filepath.write_text(old_source)
        raise ResourceError(
            f"Reload failed, rolled back: {e}",
            hints=[f"Check {module_path} for import errors"]
        )
```

### Pattern 5: Path Safety Validation
**What:** Validate module paths contain only Python identifiers, no traversal.
**When to use:** Entry point of every tool call.
**Example:**
```python
# Verified via testing in this research session
def _validate_module_path(path: str) -> None:
    """Reject paths with traversal, filesystem notation, or invalid identifiers."""
    if "/" in path or "\\" in path:
        raise ResourceError(f"Use module notation: '{path}' contains path separators")
    parts = path.split(".")
    if ".." in parts or "" in parts:
        raise ResourceError(f"Invalid module path: '{path}'")
    for part in parts:
        if not part.isidentifier():
            raise ResourceError(f"Invalid identifier '{part}' in path '{path}'")
```

### Pattern 6: SourceResourcespace as Resourcespace Protocol Implementation
**What:** The main class implementing the Resourcespace protocol with subresource children.
**When to use:** This is the root pattern; everything hangs off it.
**Example:**
```python
class SourceResourcespace:
    name = "source"
    description = "Python project source tree"

    def __init__(self, project_root: Path):
        self._root = project_root
        self._meta = MetaSubresource(self)
        self._deps = DepsSubresource(project_root)
        self._config = ConfigSubresource(project_root)
        self._tests = TestsSubresource(project_root)

    def enter(self) -> str: ...
    def nav(self) -> str: ...
    def read(self, target: str = "") -> str: ...
    def write(self, target: str, content: str = "") -> str: ...
    def edit(self, target: str, new_source: str = "") -> str: ...
    def glob(self, pattern: str = "") -> str: ...
    def grep(self, pattern: str = "", path: str = "") -> str: ...
    def supported_tools(self) -> set[str]: return {"read", "write", "edit", "glob", "grep"}
    def children(self) -> dict[str, Resourcespace]:
        return {"meta": self._meta, "deps": self._deps, "config": self._config, "tests": self._tests}
```

### Anti-Patterns to Avoid
- **Importing modules to inspect them:** Use `ast.parse(source_text)` not `import module; inspect.getmembers(module)` for read-only operations. Importing can trigger side effects and is slow.
- **File paths leaking into output:** Every output must use module paths. Never let `Path` objects or filesystem paths appear in user-facing strings.
- **Silent pruning:** The decision is explicit: when output exceeds token budget, tell the agent to narrow rather than silently truncating. Respect this by raising a narrowing hint instead of cutting content.
- **Reloading unrelated modules:** Only reload the specific module that was edited, not its importers. Cascade reload is fragile and unnecessary for the edit-test loop.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| TOML round-trip editing | Custom string manipulation of pyproject.toml | `tomlkit` | Comments, formatting, ordering are impossible to preserve manually |
| Module/package discovery | Recursive `os.walk` with `.py` filtering | `pkgutil.walk_packages()` | Handles namespace packages, `__init__.py` detection, importability checks |
| Source symbol location | Regex-based function/class finding | `ast.parse()` + node traversal | AST is correct by construction; regex breaks on decorators, multiline sigs, nested classes |
| Syntax validation | Try/except around exec() | `ast.parse()` | parse-only validation without execution side effects |
| Undo/history | Custom file-diff storage | `git stash`/`git checkout` on individual files | Git is already present, handles binary files, provides cross-session persistence |

**Key insight:** Python's `ast` module gives us everything we need for source introspection and manipulation. It provides exact line ranges (`lineno`, `end_lineno`), docstrings (`ast.get_docstring`), and full parse-validate-without-executing capability. No external library needed for the core editing pipeline.

## Common Pitfalls

### Pitfall 1: Module Path vs File Path Confusion
**What goes wrong:** Code internally works with file paths but accidentally exposes them in output, or accepts a mix of module paths and file paths.
**Why it happens:** The translation layer between module notation and filesystem is a boundary that's easy to cross accidentally.
**How to avoid:** All public-facing methods accept and return only module paths. The `_module_to_path` and `_path_to_module` functions are the ONLY bridge, used internally.
**Warning signs:** Any string containing `/` or `.py` in a return value from a tool method.

### Pitfall 2: ast.parse vs Live Module State Mismatch
**What goes wrong:** After an edit + reload, `ast.parse(file_source)` and `inspect.getsource(live_module)` may disagree if the reload failed silently or the module was imported from a different location.
**Why it happens:** Python's import system caches modules in `sys.modules` and may not always re-read from disk.
**How to avoid:** Always read source from disk (not from `inspect`), and use `importlib.reload()` explicitly after edits. For read operations, prefer `ast.parse(Path.read_text())` over `inspect.getsource()`.
**Warning signs:** Edit appears successful but `read()` shows old source.

### Pitfall 3: Reload Cascading Failures
**What goes wrong:** Reloading module A doesn't update references in module B that already imported from A. The agent sees stale behavior.
**Why it happens:** `importlib.reload(A)` re-executes A's code but B still holds its old reference to `A.SomeClass`.
**How to avoid:** Accept this limitation. The hot-reload is a convenience for the edit-test loop, not a full restart. Document that "reload updates the module; existing imports in other modules still reference the old version."
**Warning signs:** Tests pass after reload but runtime behavior uses old code.

### Pitfall 4: Symbol Replacement Indentation
**What goes wrong:** Replacing a nested symbol (method inside a class) with source that has wrong indentation.
**Why it happens:** `new_source` provided by the agent may use top-level indentation while the target is indented (e.g., a method at 4-space indent).
**How to avoid:** Detect the indentation level of the target symbol from its AST node's `col_offset` and auto-adjust the replacement source to match. Or reject mismatched indentation with a helpful error.
**Warning signs:** SyntaxError after a seemingly valid edit.

### Pitfall 5: __init__.py Auto-Update Ordering
**What goes wrong:** Adding a new module and auto-updating `__init__.py` creates import ordering issues (circular imports, forward references).
**Why it happens:** Auto-inserting an import statement without understanding the dependency graph.
**How to avoid:** Add the import at the end of `__init__.py` imports, after all existing imports. If it fails, report the circular import clearly and don't auto-add.
**Warning signs:** `ImportError` during reload after write().

### Pitfall 6: Glob/Grep Output Format
**What goes wrong:** glob/grep output uses file paths instead of module paths, breaking the semantic interface contract.
**Why it happens:** Underlying glob/grep operations work on files; results need translation.
**How to avoid:** Every result line must go through `_path_to_module()` before being included in output. Format: `bae.ai:42: def send()`.
**Warning signs:** Output containing `/` characters.

## Code Examples

### Module Summary Display (read at root level)
```python
# Uses ast.parse for static analysis without importing
def _format_module_summary(project_root: Path, module_path: str) -> str:
    filepath = _module_to_path(project_root, module_path)
    source = filepath.read_text()
    tree = ast.parse(source)

    docstring = ast.get_docstring(tree) or ""
    first_line = docstring.splitlines()[0] if docstring else ""

    classes = [n for n in ast.iter_child_nodes(tree) if isinstance(n, ast.ClassDef)]
    funcs = [n for n in ast.iter_child_nodes(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
             and not n.name.startswith("_")]

    summary = f"{module_path}"
    if first_line:
        summary += f" -- {first_line}"
    summary += f" ({len(classes)} classes, {len(funcs)} functions)"
    return summary
```

### Symbol Read (drilling into dotted paths)
```python
# read('bae.ai.Agent') shows the Agent class source
def _read_symbol(project_root: Path, dotted_path: str) -> str:
    parts = dotted_path.split(".")
    # Find where module ends and symbol begins
    for i in range(len(parts), 0, -1):
        mod_path = ".".join(parts[:i])
        try:
            filepath = _module_to_path(project_root, mod_path)
            symbol_parts = parts[i:]
            break
        except ResourceError:
            continue
    else:
        raise ResourceError(f"Module not found: {dotted_path}")

    if not symbol_parts:
        # Reading a module -- return summary or full source depending on nav state
        return filepath.read_text()

    # Find symbol in AST
    source = filepath.read_text()
    tree = ast.parse(source)
    lines = source.splitlines()
    node = _walk_to_symbol(tree, symbol_parts)
    return "\n".join(lines[node.lineno - 1:node.end_lineno])
```

### Glob with Module Paths
```python
# glob('bae.repl.*') -> list of modules matching pattern
def _module_glob(project_root: Path, pattern: str) -> str:
    import fnmatch
    # Enumerate all modules under project
    all_modules = _discover_modules(project_root)
    # Convert glob pattern: bae.repl.* -> bae.repl.*
    matches = [m for m in all_modules if fnmatch.fnmatch(m, pattern)]
    return "\n".join(sorted(matches)) or "(no matches)"
```

### Git-Based Undo
```python
# undo() reverts last edit using git
def _undo_last_edit(project_root: Path) -> str:
    import subprocess
    result = subprocess.run(
        ["git", "checkout", "--", "."],
        capture_output=True, text=True, cwd=project_root
    )
    if result.returncode != 0:
        raise ResourceError(f"Undo failed: {result.stderr}")
    return "Reverted to last committed state"
```

### Deps Subresource
```python
# source.deps() -- list/add/remove
class DepsSubresource:
    name = "deps"
    description = "Project dependencies (pyproject.toml)"

    def read(self, target: str = "") -> str:
        data = tomllib.loads(self._pyproject.read_text())
        deps = data.get("project", {}).get("dependencies", [])
        if not target:
            return "\n".join(deps)
        # Filter to matching
        return "\n".join(d for d in deps if target in d)

    def write(self, target: str, content: str = "") -> str:
        """Add a dependency: write('rich>=14.0')"""
        # Use uv add for proper resolution
        result = subprocess.run(
            ["uv", "add", target], capture_output=True, text=True,
            cwd=self._project_root
        )
        if result.returncode != 0:
            raise ResourceError(f"Failed to add {target}: {result.stderr}")
        return f"Added {target}"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `ast.parse` without end_lineno | `ast.parse` with `end_lineno` on all nodes | Python 3.8 | Enables precise symbol-level source editing without guessing where a definition ends |
| `tomllib` not in stdlib | `tomllib` in stdlib | Python 3.11 | No external dependency for reading TOML; still need `tomlkit` for writing |
| Manual pip install | `uv add`/`uv remove` | 2024 | Faster, lockfile-aware dependency management; this project already uses uv |

**Deprecated/outdated:**
- `imp` module: Replaced by `importlib` since Python 3.4. Never use `imp`.
- `setuptools`/`setup.py` for project metadata: This project uses `pyproject.toml` with `hatchling`. No setup.py parsing needed.

## Open Questions

1. **svcs for deps hotswap**
   - What we know: The CONTEXT.md says deps subresource "uses svcs for resolution under the hood." svcs is not currently a dependency of this project.
   - What's unclear: Whether to add svcs as a dependency now, or defer until a later phase when it's needed for other things too.
   - Recommendation: For MVP, use direct `uv add` + `importlib.import_module()` for deps. svcs is a service locator pattern that adds value when multiple consumers need the same dependency resolved -- not yet the case here. Add svcs when the pattern justifies it. Flag this as a discretion area.

2. **Test results as navigable subresource**
   - What we know: Tests subresource should parse pytest output into a navigable structure.
   - What's unclear: Exact structure of navigable test results (by module? by pass/fail? by test name?).
   - Recommendation: Parse pytest `-q --tb=short` output into structured format: module-grouped test names with pass/fail status. Keep it simple -- a read-only navigable tree, not a full test runner UI.

3. **Narrowing guidance vs pruning**
   - What we know: Decision says "tell agent to narrow the search rather than silently pruning."
   - What's unclear: Whether this replaces the ToolRouter's existing _prune mechanism or supplements it.
   - Recommendation: SourceResourcespace methods should detect when output exceeds budget and return a ResourceError with narrowing hints BEFORE the ToolRouter prune step runs. This way pruning is a safety net, not the primary mechanism.

## Sources

### Primary (HIGH confidence)
- Python `ast` module: Tested directly -- `ast.parse()`, `ast.get_docstring()`, `node.lineno`/`node.end_lineno`, `ast.iter_child_nodes()` all verified working on Python 3.14
- Python `importlib`: Tested directly -- `importlib.reload()` behavior verified: raises on broken imports, module object survives failed reload, old state accessible after failure
- Python `pkgutil`: Tested directly -- `walk_packages()` discovers all bae modules correctly, reports `ispkg` flag
- Python `tomllib`: Tested directly -- reads pyproject.toml, extracts dependencies, project metadata
- Python `inspect`: Tested directly -- `getsource()` returns source for classes, functions, modules

### Secondary (MEDIUM confidence)
- [tomlkit](https://github.com/python-poetry/tomlkit) -- Style-preserving TOML library. Maintained by Poetry team, 0.13.x current. Needed for writing pyproject.toml without losing comments/formatting.

### Tertiary (LOW confidence)
- svcs integration details: Not tested (not installed). The CONTEXT.md mentions it for deps hotswap but the library is not a current dependency. Deferred per recommendation above.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All core libraries tested directly on this project's Python 3.14
- Architecture: HIGH - Patterns verified via direct experimentation in this session
- Pitfalls: HIGH - Each pitfall derived from tested behavior (reload semantics, AST line numbers, path translation)

**Research date:** 2026-02-16
**Valid until:** 2026-03-16 (stable domain; stdlib APIs don't change)
