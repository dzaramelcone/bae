---
status: diagnosed
trigger: "store.sessions() fails with AttributeError because store in REPL namespace is the inspector closure from make_store_inspector(), not SessionStore instance"
created: 2026-02-13T00:00:00Z
updated: 2026-02-13T00:00:01Z
symptoms_prefilled: true
goal: find_root_cause_only
---

## Current Focus

hypothesis: CONFIRMED - store namespace binding points to inspector closure (store_fn) which only exposes search/session query functionality, not SessionStore methods
test: code analysis complete
expecting: root cause identified, recommendations ready
next_action: return diagnosis to orchestrator

## Symptoms

expected: User can call store.sessions() to list all sessions, store.recent() to see recent entries across sessions, and store() should not return ugly sqlite3.Row repr noise
actual: store.sessions() raises AttributeError; store() returns Row objects that repr as `[<sqlite3.Row object at ...>]`
errors: AttributeError when calling store.sessions()
reproduction: In REPL, call store.sessions() or store.recent()
started: Design issue - store has always been the closure, not the SessionStore instance

## Eliminated

## Evidence

- timestamp: 2026-02-13T00:00:00Z
  checked: bae/repl/store.py lines 125-141
  found: make_store_inspector() returns a closure (store_fn) that only implements query/search functionality
  implication: The closure does not expose SessionStore methods like sessions(), recent(), session_entries()

- timestamp: 2026-02-13T00:00:01Z
  checked: bae/repl/shell.py line 65
  found: self.namespace["store"] = make_store_inspector(self.store)
  implication: REPL namespace gets the closure, not the SessionStore instance itself

- timestamp: 2026-02-13T00:00:02Z
  checked: bae/repl/store.py lines 91-118
  found: SessionStore has methods: search(), recent(), sessions(), session_entries() - but only search() is exposed through the closure
  implication: Users cannot access sessions(), recent(), or session_entries() through store namespace

- timestamp: 2026-02-13T00:00:03Z
  checked: bae/repl/store.py line 139
  found: store_fn returns raw sqlite3.Row objects (entries list)
  implication: This causes ugly repr noise like `[<sqlite3.Row object at ...>]`

- timestamp: 2026-02-13T00:00:04Z
  checked: tests/repl/test_store_integration.py lines 75-96
  found: Tests verify inspector prints formatted output but returns Row objects for programmatic access
  implication: Current design intentionally returns Rows for flexibility, but this leaks implementation detail to REPL users

- timestamp: 2026-02-13T00:00:05Z
  checked: bae/repl/store.py lines 91-118
  found: All SessionStore query methods (search, recent, session_entries, sessions) return list[sqlite3.Row]
  implication: Any fix that exposes these methods will have same Row repr issue - needs holistic solution

## Resolution

root_cause: The REPL namespace binds `store` to the closure returned by `make_store_inspector()` (line 65 in shell.py), not the SessionStore instance. The closure (store_fn) only exposes two behaviors: search (when query param given) and session_entries (when no param). It does NOT expose the SessionStore methods: sessions(), recent(), session_entries(session_id). Additionally, store_fn returns raw sqlite3.Row objects which repr as ugly `<sqlite3.Row object at 0x...>` instead of formatted data.

fix: Three minimal approaches:
  1. Make SessionStore callable - Add __call__ method to SessionStore that implements the inspector behavior, then inject the instance directly
  2. Expose methods on closure - Add attributes to store_fn closure exposing store.sessions, store.recent, etc.
  3. Inject both - Add store_raw or _store to namespace alongside store inspector

Recommended: Option 1 (SessionStore callable) - Most elegant, maintains single namespace binding, follows Python conventions. SessionStore becomes its own inspector.

verification: N/A (research-only task)
files_changed:
  - bae/repl/store.py (add __call__ to SessionStore, remove make_store_inspector or repurpose it)
  - bae/repl/shell.py (inject SessionStore instance directly instead of closure)
  - tests/repl/test_store_integration.py (update inspector tests to use SessionStore directly)
