---
status: diagnosed
trigger: "ns(MyNode) crashes with NameError: name 'Annotated' is not defined when inspecting a Node subclass defined in the REPL"
created: 2026-02-13T20:30:00Z
updated: 2026-02-13T20:35:00Z
symptoms_prefilled: true
goal: find_root_cause_only
---

## Current Focus

hypothesis: "CONFIRMED - All get_type_hints() calls fail with REPL classes because they have __module__='<cortex>' and no globalns parameter is passed"
test: "Analyze fix options - local workaround in namespace.py vs systemic resolver.py changes"
expecting: "Recommend minimal fix approach"
next_action: "design minimal fix"

## Symptoms

expected: "ns(MyNode) shows class name, fields with type, kind (dep/recall/plain), and markers"
actual: "ns(MyNode) crashes with NameError: name 'Annotated' is not defined"
errors: "NameError: name 'Annotated' is not defined"
reproduction: "1. Launch cortex REPL, 2. Define Node subclass with Annotated[type, Dep()] field, 3. Call ns(MyNode)"
started: "Discovered during Phase 17 UAT testing"

## Eliminated

## Evidence

- timestamp: 2026-02-13T20:30:30Z
  checked: resolver.py classify_fields() line 40
  found: "get_type_hints(node_cls, include_extras=True)" called without globalns/localns arguments
  implication: "get_type_hints() resolves string annotations using node_cls.__module__.__dict__ as globals. REPL classes have __module__='<cortex>' which is not a real module, so no globals dict with Annotated/Dep/Recall."

- timestamp: 2026-02-13T20:30:45Z
  checked: exec.py async_exec() line 34
  found: "compiled = compile(tree, '<cortex>', 'exec', ...)" - filename is '<cortex>'"
  implication: "All REPL-defined classes get __module__='<cortex>' from the compile() filename arg. The namespace dict contains Annotated/Dep/Recall but __module__ globals don't."

- timestamp: 2026-02-13T20:31:00Z
  checked: namespace.py _inspect_node_class() line 135
  found: "classify_fields(node_cls)" called directly with just the class, no namespace context"
  implication: "classify_fields() has no way to access the REPL namespace dict that contains Annotated/Dep/Recall. It only gets the node_cls which points to '<cortex>' module."

- timestamp: 2026-02-13T20:31:15Z
  checked: typing.get_type_hints signature
  found: "get_type_hints(obj, globalns=None, localns=None, include_extras=False)"
  implication: "We can pass explicit globalns to get_type_hints() to override the __module__ globals lookup."

- timestamp: 2026-02-13T20:32:00Z
  checked: call sites of classify_fields()
  found: "4 call sites: namespace.py line 135, lm.py line 51, compiler.py line 128, and resolver.py internal uses"
  implication: "Only namespace.py is REPL-specific. lm.py and compiler.py are used during graph execution with normal modules."

- timestamp: 2026-02-13T20:32:30Z
  checked: get_type_hints() calls in resolver.py
  found: "10 calls to get_type_hints() across classify_fields, recall_from_trace, build_dep_dag, validate_node_deps, resolve_fields, _resolve_one, _build_fn_dag"
  implication: "All resolver.py functions would fail with REPL-defined classes. The issue is broader than just classify_fields."

- timestamp: 2026-02-13T20:33:00Z
  checked: lm.py build_partial_model line 52
  found: "calls get_type_hints(target_cls, include_extras=True) after classify_fields()"
  implication: "lm.py also directly calls get_type_hints and would fail with REPL classes during graph execution."

- timestamp: 2026-02-13T20:33:30Z
  checked: compiler.py node_to_signature line 129
  found: "calls get_type_hints(node_cls, include_extras=True) after classify_fields()"
  implication: "compiler.py also calls get_type_hints and would fail with REPL classes."

- timestamp: 2026-02-13T20:34:00Z
  checked: Python 3.14 annotation behavior and get_type_hints with <cortex> module
  found: "When class has __module__='<cortex>' (from compile filename), get_type_hints() fails with NameError because it looks up globals from sys.modules['<cortex>'] which doesn't exist. Passing globalns=namespace fixes it."
  implication: "Fix requires passing the REPL namespace as globalns to get_type_hints()"

## Resolution

root_cause: "Classes defined in the REPL get __module__='<cortex>' from compile(tree, '<cortex>', 'exec') in async_exec(). When any bae code calls get_type_hints() on these classes, Python looks up '<cortex>' in sys.modules to resolve string annotations. Since '<cortex>' is not a registered module, get_type_hints() fails with NameError for 'Annotated', 'Dep', 'Recall' even though they exist in the REPL namespace dict. This affects: classify_fields() (resolver.py:40), all other get_type_hints calls in resolver.py, graph.py:72, lm.py:52, compiler.py:129."

fix: "Register '<cortex>' as a module in sys.modules with the REPL namespace as its __dict__. Add _ensure_cortex_module(namespace) function in exec.py, call it in async_exec() before compile(). Update module dict on each exec to keep it in sync with REPL namespace."

verification: ""
files_changed: ["bae/repl/exec.py"]
