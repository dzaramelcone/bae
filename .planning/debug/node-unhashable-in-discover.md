---
status: diagnosed
trigger: "Node subclasses unhashable as CLASS OBJECTS in Graph._discover()"
created: 2026-02-15T16:00:00Z
updated: 2026-02-15T16:30:00Z
---

## Current Focus

hypothesis: Pydantic instances (not classes) are being passed to Graph(start=...)
test: Pass instance vs class to Graph(start=...) and compare error messages
expecting: Instance produces exact error; class works fine
next_action: Return diagnosis

## Symptoms

expected: Graph._discover() uses `if node_cls in visited:` with a set -- Node class objects should be hashable
actual: TypeError: cannot use 'examples.ootd.IsTheUserGettingDressed' as a set element (unhashable type: 'IsTheUserGettingDressed')
errors: TypeError in graph.py:193 `if node_cls in visited:`
reproduction: Pass a Node INSTANCE to Graph(start=...) instead of the class
started: Phase 26 engine foundation UAT

## Eliminated

- hypothesis: "Pydantic ModelMetaclass sets __hash__ = None, making class objects unhashable"
  evidence: "ModelMetaclass.__dict__ has no __hash__. hash() on class objects goes through type.__hash__ via object.__hash__. Verified: hash(Node), hash(IsTheUserGettingDressed), etc. all succeed."
  timestamp: 2026-02-15T16:05:00Z

- hypothesis: "Python 3.14 PEP 649 changes hash resolution for classes with __hash__ = None"
  evidence: "Tested on Python 3.14.3. Class objects are still hashable via metaclass path. PEP 649 only affects annotation evaluation, not hash/eq resolution."
  timestamp: 2026-02-15T16:10:00Z

- hypothesis: "_extract_types_from_hint returns non-type objects (ForwardRef, etc.)"
  evidence: "ForwardRef is filtered by isinstance(arg, type) guard. All successors() calls return proper type objects."
  timestamp: 2026-02-15T16:15:00Z

- hypothesis: "async_exec / _ensure_cortex_module corrupts class identity"
  evidence: "Full REPL simulation via async_exec + seed() works perfectly. Classes defined via exec are hashable and Graph construction succeeds."
  timestamp: 2026-02-15T16:20:00Z

## Evidence

- timestamp: 2026-02-15T16:05:00Z
  checked: BaseModel.__dict__['__hash__']
  found: "None -- Pydantic sets __hash__ = None because it defines __eq__"
  implication: "INSTANCES are unhashable, but CLASS OBJECTS are still hashable via metaclass"

- timestamp: 2026-02-15T16:06:00Z
  checked: "hash() on Node class objects through full metaclass MRO"
  found: "ModelMetaclass -> ABCMeta -> type -> object. Only object has __hash__. All work."
  implication: "Class objects are always hashable. The error MUST involve instances."

- timestamp: 2026-02-15T16:10:00Z
  checked: "Error message format comparison"
  found: "Instance error: 'unhashable type: ClassName'. Class error (if metaclass had __hash__=None): 'unhashable type: MetaclassName'. Reported error says 'unhashable type: IsTheUserGettingDressed' = instance."
  implication: "Error message PROVES an instance of IsTheUserGettingDressed is being passed, not the class"

- timestamp: 2026-02-15T16:15:00Z
  checked: "Graph(start=Begin(x='test')) -- passing instance instead of class"
  found: "EXACT reproduction: TypeError: cannot use 'Begin' as a set element (unhashable type: 'Begin')"
  implication: "Root cause confirmed. Graph(start=...) has no runtime type guard."

- timestamp: 2026-02-15T16:20:00Z
  checked: "All Graph(start=...) call sites in codebase"
  found: "All existing call sites pass classes correctly. No code path creates instances accidentally."
  implication: "Bug is triggered by user input (passing instance instead of class), not by internal code."

## Resolution

root_cause: |
  Graph.__init__(self, start: type[Node]) has no runtime validation that `start`
  is actually a class (not an instance). Pydantic's BaseModel sets __hash__ = None
  on the class dict (because it defines __eq__), making all BaseModel INSTANCES
  unhashable. When a user passes a Node instance instead of the class to
  Graph(start=...), _discover() tries to add the instance to a set, which fails
  with "unhashable type".

  The error message format PROVES it's an instance:
  - Instance: "unhashable type: 'IsTheUserGettingDressed'" (type(instance).__name__)
  - Class:    "unhashable type: 'ModelMetaclass'" (type(class).__name__)

  The reported error shows the NODE CLASS NAME, confirming an instance is involved.

fix: ""
verification: ""
files_changed: []
