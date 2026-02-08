# Phase 6 Plan 01: NodeConfig Redesign and _wants_lm Helper Summary

NodeConfig redesigned as standalone TypedDict with lm key; _wants_lm detects opt-in LM injection via inspect.signature

## Execution

| Task | Type | Commit | Description |
|------|------|--------|-------------|
| RED | test | e2c18a5 | Failing tests for NodeConfig TypedDict, node_config ClassVar, _wants_lm |
| GREEN | feat | 3e2de18 | Implement NodeConfig(TypedDict), node_config ClassVar, _wants_lm helper |

## What Changed

### bae/node.py
- `NodeConfig` changed from `ConfigDict` subclass to `TypedDict(total=False)` with single `lm: LM` key
- Old `model`/`temperature` keys removed (those belonged to Pydantic config space, not bae config)
- `Node` class now has separate `model_config = ConfigDict(arbitrary_types_allowed=True)` and `node_config: ClassVar[NodeConfig] = NodeConfig()`
- `Node` class declaration changed from `Node(BaseModel, arbitrary_types_allowed=True)` to `Node(BaseModel)` since model_config handles that now
- Added `_wants_lm(method) -> bool` using `inspect.signature` to detect `lm` parameter presence
- Added `TypedDict` to typing imports
- All existing functionality preserved (Node.__call__ still takes lm, successors/is_terminal unchanged)

### tests/test_node_config.py (new)
- 14 tests covering: NodeConfig as TypedDict, node_config ClassVar inheritance/isolation, _wants_lm detection

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| `_wants_lm` uses `inspect.signature` not AST | Signature inspection is simpler and handles bound/unbound methods uniformly |
| NodeConfig `lm` field typed under TYPE_CHECKING | Avoids circular import at runtime; LM type only needed for static analysis |
| Removed `arbitrary_types_allowed=True` from class signature | Moved to explicit `model_config = ConfigDict(...)` for clarity alongside `node_config` |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed TypedDict issubclass test**
- **Found during:** GREEN phase
- **Issue:** `issubclass(NodeConfig, ConfigDict)` raises `TypeError` because TypedDict doesn't support instance/class checks
- **Fix:** Changed test to check `ConfigDict not in NodeConfig.__bases__` instead
- **Files modified:** tests/test_node_config.py

## Verification

- `tests/test_node_config.py`: 14/14 pass
- `tests/test_node.py`: 8/8 pass (unchanged)
- `tests/test_auto_routing.py`: 19/19 pass (unchanged)
- Full suite (excluding pre-existing RED tests): 195 pass, 0 fail

## Notes

- Pre-existing RED-phase tests exist for plans 06-02 (test_signature_v2.py) and 06-03 (test_result_v2.py) -- these fail as expected
- The base Node.__call__ signature still has `lm` parameter -- preserved for backward compat per plan instructions
- `_wants_lm` will be consumed by Phase 7's execution loop to distinguish auto-route vs escape-hatch nodes
