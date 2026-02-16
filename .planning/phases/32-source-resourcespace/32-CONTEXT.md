# Phase 32: Source Resourcespace - Context

**Gathered:** 2026-02-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Source resourcespace: a semantic Python project interface. The agent navigates Python modules, packages, and project subresources (deps, config, tests) — not raw files. All addressing uses Python module notation (bae.ai, bae.cortex.shell). This phase proves the resourcespace pattern end-to-end with a concrete, useful implementation.

</domain>

<decisions>
## Implementation Decisions

### Module-based addressing
- All paths use Python module notation: `read('bae.ai')`, `glob('bae.cortex.*')`
- No raw file paths — source is a semantic interface over the Python project
- Non-Python package data (templates, data files) also accessible within the module tree
- Dotted paths drill into symbols: `read('bae.ai.Agent')` shows the Agent class source
- Navigation also works: `source.bae.ai()` enters the module, then `read('Agent')` for details
- Both approaches work — dotted reads for quick lookups, navigation for exploration

### Module display
- `read()` on a module from root level shows: high-level interface summary — major methods/functions/types, docstrings truncated to 1 line
- `read()` when navigated inside a module shows full source
- Module summaries include docstring (1 line) + class/function counts: `bae.ai — AI agent core (3 classes, 12 functions)`
- Glob/grep results use module paths: `bae.ai:42: def send()`
- Package hierarchy uses standard tree navigation — see current level, navigate deeper

### Path safety
- Traversal escapes (`../`) and out-of-scope paths rejected with clear ResourceError
- No filesystem paths exposed — the module-based interface is the only addressing scheme

### Entry experience
- `source()` entry shows: subresources (deps, config, tests) + brief descriptions
- Packages discoverable via `read()` which shows top-level packages with docstring + counts
- When output exceeds token budget, tell agent to narrow the search rather than silently pruning

### Subresources
- `source.deps()` — list/add/remove dependencies. Modifies pyproject.toml, hotswaps module at runtime, uses svcs for resolution under the hood
- `source.config()` — structured access to pyproject.toml sections only
- `source.tests()` — browse test modules + run tests. Test results are a navigable subresource
- `source.meta()` — read/edit the SourceResourcespace implementation itself (MVP scope)

### Edit operations
- Write/edit work from any navigation level (no navigate-first requirement)
- Semantic edits: `edit('bae.ai.Agent.send', new_source=...)` — symbol-level, not string replacement
- `write()` for new modules accepts raw Python source; auto-updates `__init__.py` to expose new module
- Syntax validation via `ast.parse` before writing — reject invalid Python
- Auto hot-reload after edit via `importlib.reload()`
- If reload fails (import error, circular deps): auto rollback to last-good state, report helpful error describing what went wrong

### Undo + history
- Source provides an undo affordance — implementation details (git, rope, etc.) abstracted behind the interface
- Git only for persistent history is fine; undo is an operational convenience

### Claude's Discretion
- Navigation chrome (breadcrumbs, sibling display when inside a package)
- Exact pruning strategy for narrowing guidance
- Internal tool translation (module patterns → file operations under the hood)
- Rope vs AST vs other libraries for semantic editing internals

</decisions>

<specifics>
## Specific Ideas

- Resources are interfaces — the representation can be shaped as the agent uses it
- "Everything should work the way you'd expect" — draw from existing file system and source tree navigation precedent
- Hot reload with auto-rollback makes the edit cycle tight: edit → reload → success or rollback+error
- Test results as a navigable subresource — not just raw pytest output
- Deps hotswap at runtime using svcs for dependency resolution

</specifics>

<deferred>
## Deferred Ideas

- meta() as a full representation-tuning interface (configurable display, affordance control) — pattern established here, fleshed out across all resourcespaces later
- Non-Python config files (.env, etc.) — pyproject.toml only for now

</deferred>

---

*Phase: 32-source-resourcespace*
*Context gathered: 2026-02-16*
